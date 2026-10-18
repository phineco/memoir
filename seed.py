"""灌样本数据：王家（王德顺 / 王建军 / 王秀兰 / 李桂香），直接看效果。"""
import datetime

from werkzeug.security import generate_password_hash

from config import Config
from models import (Comment, Draft, Family, FamilyMember, Interview, InterviewPerson, Like, NewPerson,
                    Person, PersonLink, Photo, Portrait, Quote, ShareSnapshot,
                    SourceFile, TimelineEvent, Transcript, User, VerificationItem,
                    get_session, init_db, new_id)

init_db(Config.DATABASE_URL)
s = get_session()
now = datetime.datetime.now()

# 清空重灌（原型用）
for m in (ShareSnapshot, Portrait, Photo, TimelineEvent, NewPerson, PersonLink, FamilyMember,
          VerificationItem, Quote, Draft, Interview, Transcript, SourceFile,
          Person, Family, User):
    s.query(m).delete()
s.commit()

u = User(id=new_id(), phone="13800000000", nickname="主持人",
         password_hash=generate_password_hash("demo123"))
u2 = User(id=new_id(), phone="13900000000", nickname="大姑",
          password_hash=generate_password_hash("demo123"))
fam = Family(id="wang", name="王家", owner_user_id=u.id)
fm1 = FamilyMember(id=new_id(), family_id="wang", user_id=u.id, role="owner")
fm2 = FamilyMember(id=new_id(), family_id="wang", user_id=u2.id, role="admin")

p01 = Person(id="p01", parent_id="0", parent_ids="0,", family_id="wang", name="王德顺",
             aliases=["爷爷"], relation="爷爷", generation=0, birth_year=1935,
             death_year=2005, alive=False, status="verified", sort=1, gender="M", spouse_id="p04",
             notes=["16岁参军", "转业后在县机械厂"])
p02 = Person(id="p02", parent_id="p01", parent_ids="0,p01,", family_id="wang", name="王建军",
             aliases=["三叔"], relation="三叔", generation=1, birth_year=1962,
             alive=True, status="drafted", sort=1, gender="M", notes=["县城供销社上班"])
p03 = Person(id="p03", parent_id="p01", parent_ids="0,p01,", family_id="wang", name="王秀兰",
             relation="姑姑", generation=1, birth_year=1958, alive=True, gender="F",
             status="doing", sort=2, notes=["家里故事讲得最多的人"])
p04 = Person(id="p04", parent_id="p01", parent_ids="0,p01,", family_id="wang", name="李桂香",
             aliases=["奶奶"], relation="奶奶", generation=0, birth_year=1938,
             death_year=2018, alive=False, gender="F", status="pending", sort=2, spouse_id="p01")

src = SourceFile(id=new_id(), family_id="wang", uploader_id=u.id,
                 file_name="三叔供销社.m4a", file_type="audio",
                 file_size=12345678, duration_sec=1260,
                 storage_path="oss://memoir/wang/src-20261016-01.m4a",
                 file_hash="abc123")
tr = Transcript(id=new_id(), source_file_id=src.id, version=1,
                content="（转写文字稿略）三叔说，1978年他进了县供销社……",
                asr_engine="asr-v1", confidence=0.93)

iv1 = Interview(id="iv1", family_id="wang", source_file_id=src.id, transcript_id=tr.id,
                person_id="p02", topic="供销社的那些年", prompt_version="v3",
                llm_model="demo", status="done", publish_status="published", create_date=now,
                narrator_person_id="p02",
                period_start=datetime.date(1978, 1, 1), period_end=datetime.date(1990, 12, 31),
                period_precision="year")
iv2 = Interview(id="iv2", family_id="wang", source_file_id=src.id, transcript_id=tr.id,
                person_id="p01", topic="爷爷的童年", prompt_version="v3",
                llm_model="demo", status="done", publish_status="published", create_date=now,
                narrator_person_id="p03",
                period_start=datetime.date(1935, 1, 1), period_end=datetime.date(1950, 12, 31),
                period_precision="year")

d1 = Draft(id=new_id(), interview_id="iv1", version=1, is_current=True, create_date=now,
           content="""# 供销社的那些年

1978年秋天，王建军揣着大队开的介绍信，第一次走进了县供销社的大门。那年他十六岁，个子还没柜台高，主任让他先从搬货干起。

"第一天就搬了二百多箱汽水，"三叔回忆说，"晚上胳膊都抬不起来，但心里头高兴——咱也是吃商品粮的人了。"

在供销社的十二年，是三叔人生中最踏实的十二年。他从搬运工干到营业员，又干到门市部的会计。1985年，供销社第一次有了电视机专柜，三叔负责登记排队买电视的人，一本册子记得密密麻麻。"那时候一台黑白电视要排三个月，谁家能买上一台，整条街都去看。"

1990年，供销社改制。三叔拿着三千块钱补偿金，在街口摆了个五金摊。"铁饭碗碎了，但手艺和人缘碎不了。"如今提起那段日子，三叔还是那句话：做生意和做人一样，实在才能长久。""")

quotes = [
    Quote(id=new_id(), interview_id="iv1", text="铁饭碗碎了，但手艺和人缘碎不了。", status="kept"),
    Quote(id=new_id(), interview_id="iv1", text="那时候一台黑白电视要排三个月，谁家能买上一台，整条街都去看。", status="kept"),
]
verifs = [
    VerificationItem(id=new_id(), interview_id="iv1",
                     text="1978年秋天进了县供销社", reason="入职年份需核实：介绍信存根",
                     person_id="p02", status="pending"),
    VerificationItem(id=new_id(), interview_id="iv1",
                     text="三叔全名", reason="确认是否为王建军",
                     person_id="p02", status="resolved", correction="已确认为王建军"),
]
links = [
    PersonLink(id=new_id(), interview_id="iv1", mention="三叔", person_id="p02",
               is_new=False, status="linked"),
    PersonLink(id=new_id(), interview_id="iv1", mention="张大爷", person_id=None,
               is_new=True, status="pending_confirm"),
]
newp = NewPerson(id=new_id(), family_id="wang", interview_id="iv1", name="张大爷",
                 context="供销社的老同事，常和三叔一起下乡收购", join_tree="pending")

events = [
    TimelineEvent(id=new_id(), family_id="wang", person_id="p02",
                  event_date=datetime.date(1978, 10, 1), date_precision="month",
                  title="进入县供销社", description="揣着大队介绍信，第一天搬了二百多箱汽水。",
                  source_interview_id="iv1"),
    TimelineEvent(id=new_id(), family_id="wang", person_id="p02",
                  event_date=datetime.date(1985, 1, 1), date_precision="year",
                  title="负责电视机专柜登记", description="一本册子记得密密麻麻，排队三个月才能买到电视。",
                  source_interview_id="iv1"),
    TimelineEvent(id=new_id(), family_id="wang", person_id="p02",
                  event_date=datetime.date(1990, 1, 1), date_precision="year",
                  title="供销社改制，摆五金摊", description="拿着三千块补偿金在街口摆摊。",
                  source_interview_id="iv1"),
    TimelineEvent(id=new_id(), family_id="wang", person_id="p02",
                  event_date=None, date_precision="year",
                  title="和张大爷下乡收购（时间待定）", description="年份不确定，待下次采访追问。",
                  source_interview_id="iv1"),
]
photos = [
    Photo(id=new_id(), family_id="wang", person_id="p02", photo_year=1985,
          caption="供销社门市部旧照", uploaded_by=u.id),
    Photo(id=new_id(), family_id="wang", person_id="p02", photo_year=1992,
          caption="五金摊开张", uploaded_by=u.id),
]
portrait = Portrait(id=new_id(), person_id="p02", version=1,
                    profile_text="""王建军，1962年生，王家第三代。1978年进入县供销社，从搬运工干到会计；1990年改制后摆五金摊至今。

性格实在、话不多，认"实在才能长久"的理（来源：iv1 初稿）。待核实：入职年份1978年是否准确（verification 待核实第1条）。""")

snap = ShareSnapshot(
    id=new_id(), family_id="wang", title="王家 · 回忆录（第1周）",
    token="wang-week1", password_hash=generate_password_hash("jiayou123"),
    status="published",
    content_json={
        "title": "王家 · 回忆录（第1周）",
        "new_badge": "本周新增：《供销社的那些年》",
        "stories": [{"title": "供销社的那些年", "person": "王建军",
                     "summary": "1978年进供销社，1990年改制后摆五金摊。"}],
        "quotes": ["铁饭碗碎了，但手艺和人缘碎不了。"],
        "tree_note": "家族树：王德顺（爷爷）→ 王建军（三叔）、王秀兰（姑姑）；李桂香（奶奶）待采访。",
    })

# 示例草稿（主持人手写，未发布，仅作者可见）
ivd = Interview(id="ivd", family_id="wang", author_id=u.id, person_id="p04",
                topic="奶奶的针线活", status="done", publish_status="draft",
                period_start=datetime.date(1960, 1, 1),
                period_end=datetime.date(1980, 12, 31), period_precision="year")
dd = Draft(id=new_id(), interview_id="ivd", version=1, is_current=True,
           content="<p>奶奶的针线笸箩，一年四季摆在炕头。冬天纳鞋底，夏天缝单衣，针脚细得像印上去的。</p><p>我小时候的棉袄、棉裤，全是她一针一线缝出来的，穿旧了拆了重做，一点不浪费。</p>",
           create_by=u.id, create_date=now)
ipd1 = InterviewPerson(id=new_id(), interview_id="ivd", person_id="p04", role="subject")
ipd2 = InterviewPerson(id=new_id(), interview_id="ivd", person_id="p03", role="related")

s.add_all([u, u2, fam, fm1, fm2, p01, p02, p03, p04, src, tr, iv1, iv2, d1, newp, portrait, snap]
          + quotes + verifs + links + events + photos + [ivd, dd, ipd1, ipd2])

# 故事关联人物（人物线串联）
ip1 = InterviewPerson(id=new_id(), interview_id="iv1", person_id="p02", role="subject")
ip2 = InterviewPerson(id=new_id(), interview_id="iv1", person_id="p03", role="related")
ip3 = InterviewPerson(id=new_id(), interview_id="iv2", person_id="p01", role="subject")
ip4 = InterviewPerson(id=new_id(), interview_id="iv2", person_id="p03", role="related")
s.add_all([ip1, ip2, ip3, ip4])

# 大姑认领王秀兰（演示人物-账号关联）
p03.user_id = u2.id

# 示例评论（含一条追评）
c1 = Comment(id=new_id(), interview_id="iv1", user_id=u2.id, parent_id="0",
             content="三叔这段写得真好，看得我眼眶都热了。", like_count=1)
s.add(c1)
s.flush()
c2 = Comment(id=new_id(), interview_id="iv1", user_id=u.id, parent_id=c1.id,
             content="是啊，特别是改制摆摊那段，太不容易了。")
s.add(c2)
s.add(Like(id=new_id(), target_type="comment", target_id=c1.id, user_id=u.id))
s.add(Like(id=new_id(), target_type="interview", target_id="iv1", user_id=u2.id))
iv1.like_count = 1
iv1.view_count = 128
s.commit()
print("seed ok: 家庭=王家, 人物=4, 故事=2, 分享 token=wang-week1 / 密码=jiayou123, 登录 13800000000/demo123")
