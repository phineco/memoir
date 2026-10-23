"""UI 回归专用服务：始终使用临时 SQLite，不读取或修改项目数据库。"""
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_workspace = tempfile.TemporaryDirectory(prefix="memoir-ui-data-")
os.environ.update(DATABASE_URL="sqlite:///" + str(Path(_workspace.name) / "ui.db"), APP_ENV="local", SMS_DEVELOPMENT_MODE="1",
                  SECRET_KEY="local-ui-test-only", DEEPSEEK_API_KEY="",
                  ALIYUN_SMS_ACCESS_KEY_ID="", ALIYUN_SMS_SIGN_NAME="", ALIYUN_SMS_TEMPLATE_CODE="",
                  STORAGE_BACKEND="local", UPLOAD_DIR=str(Path(_workspace.name) / "uploads"))

from app import app
import ai
import models
from models import (AiMessage, Comment, Draft, Family, FamilyMember, Interview,
                    Person, Portrait, TimelineEvent, User, Invite, VerificationItem, get_session)
from werkzeug.security import generate_password_hash

models.Base.metadata.create_all(models._engine)
s = get_session()
s.add(User(id="ui-user", username="ui-test", nickname="测试家人",
           password_hash=generate_password_hash("ui-test-only")))
for fid, name in [("ui", "岁月里的家"), ("empty", "等待第一段故事的家")]:
    s.add(Family(id=fid, name=name, owner_user_id="ui-user"))
    s.add(FamilyMember(id="member-"+fid, family_id=fid, user_id="ui-user", role="owner"))
s.add(User(id="ui-relative", username="ui-relative", nickname="另一位家人"))
s.add(FamilyMember(id="member-relative", family_id="ui", user_id="ui-relative", role="member"))
s.add(Person(id="grandma", family_id="ui", name="林奶奶", gender="F", birth_year=1942, alive=True, status="drafted", notes=["喜欢讲童年的事"]))
s.add(Person(id="daughter", family_id="ui", name="林妈妈", parent_id="grandma", parent_ids="0,grandma,", gender="F", birth_year=1968, alive=True))
s.add(Interview(id="story", family_id="ui", topic="奶奶的老院子与那个很长很长的夏天", author_id="ui-user", person_id="grandma", narrator_person_id="grandma", publish_status="published", visibility="public"))
s.add(Draft(id="draft", interview_id="story", version=1, is_current=True,
            content="<p>夏天的傍晚，奶奶坐在院子里，给我们讲她小时候的故事。</p><p>这些平凡的日子，是一家人最珍贵的记忆。</p>"))
s.add(VerificationItem(id="verify-ui", interview_id="story", text="老院子在哪一年搬入",status="pending"))
s.add(Portrait(id="portrait", person_id="grandma", version=1, profile_text="她用一双勤劳的手，把一家人的日子过得温暖。"))
s.add(TimelineEvent(id="event", family_id="ui", person_id="grandma", title="搬进老院子", date_precision="year"))
for depth in range(14):
    s.add(Comment(id=f"comment-{depth}", interview_id="story", user_id="ui-user",
                  parent_id=f"comment-{depth-1}" if depth else "0",
                  content="这段回忆我也记得。" + ("长文字"*24 if depth == 5 else "")))
s.add(AiMessage(id="message", family_id="ui", user_id="ui-user", role="assistant", content="可以从一张老照片开始，聊聊照片里的人和那一天的事。"))
import datetime
s.add(Invite(id="ui-invite",family_id="ui",code="ui-invite-only",max_uses=5,used_count=0,
             expire_at=datetime.datetime.now()+datetime.timedelta(days=7)))
s.commit()
ai.ai_enabled = lambda: True  # 展示界面；底层 key 为空，无法调用真实模型。

if __name__ == "__main__":
    import logging
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    app.run(host="127.0.0.1", port=int(os.environ.get("UI_TEST_PORT", "5015")), debug=False)
