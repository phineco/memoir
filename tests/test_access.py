import datetime
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from ai import AIError, family_knowledge
from config import Config
from models import (Comment, Draft, Family, FamilyMember, Interview, Invite, Like,
                    Person, Photo, ShareSnapshot, SyncLog, TimelineEvent,
                    VerificationItem, get_session)


@pytest.mark.parametrize("path", [
    "/f/b", "/f/b/person/pb", "/f/b/stories", "/f/b/story/public-b",
    "/f/b/weekly", "/f/b/write", "/f/b/ask", "/f/b/plans", "/f/b/sync",
    "/api/weekly-report?family_id=b", "/api/writing-plan?family_id=b",
])
def test_cross_family_reads_are_denied(client, login, path):
    login()
    assert client.get(path).status_code == 404


def test_index_only_lists_memberships_and_legacy_owner(client, login):
    login()
    body = client.get("/").get_data(as_text=True)
    assert "Alpha Family" in body
    assert "Beta Secret Family" not in body
    s = get_session()
    s.add(Family(id="legacy", name="Legacy Family", owner_user_id="owner-a"))
    s.commit()
    assert client.get("/f/legacy").status_code == 200


@pytest.mark.parametrize("path", [
    "/api/writing-plan?family_id=a", "/api/weekly-report?family_id=a",
])
def test_apis_require_login(client, path):
    assert client.get(path).status_code == 401


def test_removed_member_loses_all_family_access(client, login):
    login("member-a")
    assert client.get("/f/a").status_code == 200
    s = get_session()
    s.query(FamilyMember).filter_by(id="member").one().del_flag = 1
    s.commit()
    assert client.get("/f/a").status_code == 404
    assert "Alpha Family" not in client.get("/").get_data(as_text=True)


def test_member_cannot_read_private_story_or_like_it(client, login):
    login("member-a")
    assert client.get("/f/a/story/public-a").status_code == 200
    assert client.get("/f/a/story/specific-a").status_code == 200
    assert client.get("/f/a/story/private-a").status_code == 404
    assert client.get("/f/a/story/draft-a").status_code == 404
    assert client.post("/api/like", json={"target_type": "interview", "target_id": "private-a"}).status_code == 404
    login("outsider")
    assert client.get("/f/a/story/specific-a").status_code == 404


@pytest.mark.parametrize("target_type,target_id", [("interview", "public-b"), ("comment", "cb")])
def test_cross_family_likes_are_denied(client, login, target_type, target_id):
    login()
    assert client.post("/api/like", json={"target_type": target_type, "target_id": target_id}).status_code == 404
    assert get_session().query(Like).count() == 0


def test_like_can_be_toggled_repeatedly(client, login):
    login()
    for expected in (True, False, True):
        data = client.post("/api/like", json={"target_type": "interview", "target_id": "public-a"}).get_json()
        assert data["liked"] is expected
        assert data["count"] == int(expected)
    assert get_session().query(Like).count() == 1


def test_cross_family_writes_and_forged_person_links_are_denied(client, login):
    login()
    data = {"topic": "intrusion", "content": "hello", "action": "publish"}
    assert client.post("/f/b/write", data=data).status_code == 404
    for field in ("subject_id", "related_ids"):
        assert client.post("/f/a/write", data={**data, field: "pb"}).status_code == 400
    assert not get_session().query(Interview).filter_by(topic="intrusion").first()


def test_replies_cannot_attach_to_other_stories(client, login):
    login()
    assert client.post("/f/a/story/public-a/comment", data={"content": "bad reply", "parent_id": "cb"}).status_code == 400
    assert not get_session().query(Comment).filter_by(content="bad reply").first()


def test_local_photos_check_membership_and_deleted_records(client, login):
    path = Path(Config.UPLOAD_DIR) / "a/pa/photo.png"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"test-photo")
    s = get_session()
    s.add(Photo(id="photo", family_id="a", person_id="pa", storage_path="a/pa/photo.png"))
    s.commit()
    assert client.get("/uploads/a/pa/photo.png").status_code == 401
    login("owner-b")
    assert client.get("/uploads/a/pa/photo.png").status_code == 404
    login("member-a")
    response = client.get("/uploads/a/pa/photo.png")
    assert response.data == b"test-photo"
    assert response.headers["Cache-Control"] == "private, no-store"
    s.query(Photo).filter_by(id="photo").one().del_flag = 1
    s.commit()
    assert client.get("/uploads/a/pa/photo.png").status_code == 404


def test_ai_knowledge_respects_story_visibility(app):
    member_text = family_knowledge("a", "member-a")
    assert "quote-public-a" in member_text
    assert "quote-specific-a" in member_text
    for secret in ("private-a", "draft-a", "public-b"):
        assert secret not in member_text
    assert "quote-private-a" in family_knowledge("a", "owner-a")
    public_text = family_knowledge("a")
    assert "specific-a" not in public_text
    assert "private-a" not in public_text
    with pytest.raises(AIError):
        family_knowledge("b", "owner-a")


def test_timeline_follows_source_story_visibility(client, login):
    s = get_session()
    s.add(TimelineEvent(id="secret-event", family_id="a", person_id="pa", title="Hidden Event", source_interview_id="private-a"))
    s.commit()
    login("member-a")
    assert "Hidden Event" not in client.get("/f/a/person/pa").get_data(as_text=True)
    login()
    assert "Hidden Event" in client.get("/f/a/person/pa").get_data(as_text=True)


@pytest.mark.parametrize("kind", ["verification_update", "revision_sync"])
def test_sync_cannot_modify_another_family(client, login, kind):
    login()
    payload = {"interview_id": "public-b", "item_id": "v-public-b", "status": "resolved"}
    if kind == "revision_sync":
        payload = {"revisions": [{"kind": "draft", "interview_id": "public-b", "draft": "stolen"}]}
    response = client.post("/api/sync", json={"family_id": "a", "packet": {"type": kind, "clientId": "attack", "payload": payload}})
    assert response.status_code == 400
    s = get_session()
    assert s.query(VerificationItem).filter_by(id="v-public-b").one().status == "pending"
    assert s.query(Draft).filter_by(interview_id="public-b", is_current=True).one().content == "content-public-b"
    assert s.query(SyncLog).filter_by(status="failed").count() == 1


def test_failed_sync_rolls_back_earlier_revisions(client, login):
    login()
    revisions = [
        {"kind": "verify", "action": "confirm", "interview_id": "public-a", "item_id": "v-public-a"},
        {"kind": "draft", "interview_id": "public-b", "draft": "forbidden"},
    ]
    response = client.post("/api/sync", json={"family_id": "a", "packet": {"type": "revision_sync", "clientId": "mixed", "payload": {"revisions": revisions}}})
    assert response.status_code == 400
    assert get_session().query(VerificationItem).filter_by(id="v-public-a").one().status == "pending"


def test_member_management_does_not_enumerate_outside_accounts(client, login):
    login()
    assert "Beta Secret User" not in client.get("/f/a").get_data(as_text=True)
    assert "Beta Secret User" not in client.get("/f/a/tree/pa/edit").get_data(as_text=True)
    assert client.post("/f/a/tree/pa/edit", data={"name": "Alpha Person", "link_user_id": "owner-b"}).status_code == 400


def test_owner_can_add_an_existing_user_by_exact_login(client, login):
    login()
    assert client.post("/f/a/members/add", data={"login_id": "outsider", "role": "member"}).status_code == 302
    login("outsider")
    assert client.get("/f/a").status_code == 200


def test_member_cannot_import_or_manage_the_family(client, login):
    login("member-a")
    assert client.post("/api/sync", json={"family_id": "a", "packet": {}}).status_code == 403
    assert client.post("/api/sync", json={"family_id": "b", "packet": {}}).status_code == 404
    assert client.post("/f/a/members/add", data={"login_id": "outsider"}).status_code == 403


def test_invites_and_published_password_shares_still_work(client, login):
    s = get_session()
    s.add(Invite(id="invite", family_id="a", code="join-a", max_uses=2, expire_at=datetime.datetime.now() + datetime.timedelta(days=1)))
    s.add(ShareSnapshot(id="snap", family_id="a", token="share-a", status="published", password_hash=generate_password_hash("test-password"), content_json={"title": "Shared Title"}))
    s.add(ShareSnapshot(id="draft-snap", family_id="a", token="draft-share", status="draft"))
    s.commit()
    assert client.get("/s/draft-share").status_code == 404
    assert "Shared Title" not in client.get("/s/share-a").get_data(as_text=True)
    assert "Shared Title" in client.post("/s/share-a", data={"password": "test-password"}).get_data(as_text=True)
    login("outsider")
    assert client.get("/f/a").status_code == 404
    assert client.get("/join/join-a").status_code == 302
    assert client.get("/f/a").status_code == 200
