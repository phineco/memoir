import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# app 模块会创建默认应用；测试导入时只允许连接内存数据库。
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["DEEPSEEK_API_KEY"] = ""

import models
from app import create_app
from config import Config


@pytest.fixture
def app(tmp_path, monkeypatch):
    models._Session.remove()
    models._engine.dispose()
    monkeypatch.setattr(Config, "DATABASE_URL", "sqlite://")
    monkeypatch.setattr(Config, "UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(Config, "APP_ENV", "local")
    monkeypatch.setattr(Config, "SMS_DEVELOPMENT_MODE", True)
    monkeypatch.setattr(Config, "SMS_ENABLED", False)
    monkeypatch.setattr(Config, "VOICE_ENABLED", False)
    monkeypatch.setattr(Config, "VOICE_COMPLIANCE_APPROVED", False)
    monkeypatch.setattr(Config, "VOICE_API_KEY", '')
    application = create_app()
    application.config.update(TESTING=True, SECRET_KEY="test-only-secret")
    # Test provisioning is explicit; application workers never perform DDL.
    models.Base.metadata.create_all(models._engine)
    s = models.get_session()
    s.add_all([
        models.User(id="owner-a", username="owner-a", nickname="Alpha Owner"),
        models.User(id="member-a", username="member-a", nickname="Alpha Member"),
        models.User(id="owner-b", username="owner-b", nickname="Beta Secret User"),
        models.User(id="outsider", username="outsider", nickname="Outsider"),
        models.Family(id="a", name="Alpha Family", owner_user_id="owner-a"),
        models.Family(id="b", name="Beta Secret Family", owner_user_id="owner-b"),
        models.FamilyMember(id="ma", family_id="a", user_id="owner-a", role="owner"),
        models.FamilyMember(id="member", family_id="a", user_id="member-a", role="member"),
        models.FamilyMember(id="mb", family_id="b", user_id="owner-b", role="owner"),
        models.Person(id="pa", family_id="a", name="Alpha Person"),
        models.Person(id="pb", family_id="b", name="Beta Person"),
    ])
    for sid, fid, author, visibility, status in [
        ("public-a", "a", "owner-a", "public", "published"),
        ("private-a", "a", "owner-a", "private", "published"),
        ("specific-a", "a", "owner-a", "specific", "published"),
        ("draft-a", "a", "owner-a", "public", "draft"),
        ("public-b", "b", "owner-b", "public", "published"),
    ]:
        s.add(models.Interview(id=sid, family_id=fid, author_id=author,
                              topic=sid, visibility=visibility, publish_status=status))
        s.add(models.Draft(id="d-" + sid, interview_id=sid, version=1,
                           is_current=True, content="content-" + sid))
        s.add(models.Quote(id="q-" + sid, interview_id=sid, text="quote-" + sid))
        s.add(models.VerificationItem(id="v-" + sid, interview_id=sid,
                                      text="verify-" + sid, status="pending"))
    s.add(models.InterviewViewer(id="viewer", interview_id="specific-a", user_id="member-a"))
    s.add(models.Comment(id="ca", interview_id="public-a", user_id="owner-a", content="hello"))
    s.add(models.Comment(id="cb", interview_id="public-b", user_id="owner-b", content="secret"))
    s.add(models.WritingPlan(id="plan-b", family_id="b", title="Beta Plan", status="active", items="[]"))
    s.commit()
    yield application
    models._Session.remove()
    models._engine.dispose()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def login(client):
    def as_user(uid="owner-a"):
        with client.session_transaction() as session:
            session.clear()
            session["user_id"] = uid
        return client
    return as_user
