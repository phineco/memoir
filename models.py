"""SQLAlchemy 模型：与 memoir-mysql-schema.sql 业务表对应。

约定：
- id 由应用生成（uuid4 hex），与 SQL 中 varchar(64) 主键一致；
- del_flag：0=显示，1=隐藏（SQL 模板为 DEFAULT NULL，原型中默认 0 便于查询）；
- persons 为树形结构（parent_id / parent_ids / sort），参考 sys_area 模式。
"""
import datetime
import uuid

from sqlalchemy import (
    JSON, BigInteger, Boolean, Column, Date, DateTime, Integer, Numeric,
    String, Text, UniqueConstraint, create_engine, event, Index, inspect,
)
from sqlalchemy.orm import declarative_base, scoped_session, sessionmaker
from sqlalchemy.engine import make_url
from sqlalchemy.dialects.mysql import MEDIUMTEXT

Base = declarative_base()


def new_id() -> str:
    return uuid.uuid4().hex


class AuditMixin:
    id = Column(String(64), primary_key=True, default=new_id)
    create_by = Column(String(64))
    create_date = Column(DateTime, default=datetime.datetime.now)
    update_by = Column(String(64))
    update_date = Column(DateTime, default=datetime.datetime.now,
                         onupdate=datetime.datetime.now)
    remarks = Column(String(255))
    del_flag = Column(Integer, default=0)


class User(AuditMixin, Base):
    __tablename__ = "users"
    wechat_openid = Column(String(64), unique=True)
    phone = Column(String(20), unique=True)
    username = Column(String(32), unique=True)  # 用户名登录（管理员可为家人开通）
    nickname = Column(String(64))
    name = Column(String(64))  # 真实姓名（为家人开通账号时必填）
    password_hash = Column(String(128))  # 原型用手机号/用户名+密码登录；生产换微信 OAuth


class Family(AuditMixin, Base):
    __tablename__ = "families"
    name = Column(String(64))
    owner_user_id = Column(String(64))  # 创建者；权限明细见 family_members


class FamilyMember(AuditMixin, Base):
    """家庭成员与角色：一个家庭可有多个管理员，权限按家庭隔离。"""
    __tablename__ = "family_members"
    family_id = Column(String(64), index=True)
    user_id = Column(String(64), index=True)
    role = Column(String(16), default="member")  # owner=创建者 admin=管理员 member=普通成员
    __table_args__ = (UniqueConstraint("family_id", "user_id",
                                       name="uk_family_member"),)


class Person(AuditMixin, Base):
    __tablename__ = "persons"
    parent_id = Column(String(64), nullable=False, default="0")
    parent_ids = Column(String(2000), nullable=False, default="0,")
    family_id = Column(String(64), index=True)
    name = Column(String(100), nullable=False)
    aliases = Column(JSON)
    relation = Column(String(64))
    generation = Column(Integer)
    birth_year = Column(Integer)
    death_year = Column(Integer)
    birth_calendar = Column(String(8), default="solar")  # solar=公历 lunar=农历
    death_calendar = Column(String(8), default="solar")
    birth_solar_year = Column(Integer)
    birth_solar_month = Column(Integer)
    birth_solar_day = Column(Integer)
    birth_lunar_year = Column(Integer)
    birth_lunar_month = Column(Integer)
    birth_lunar_day = Column(Integer)
    birth_lunar_leap = Column(Boolean, default=False)
    death_solar_year = Column(Integer)
    death_solar_month = Column(Integer)
    death_solar_day = Column(Integer)
    death_lunar_year = Column(Integer)
    death_lunar_month = Column(Integer)
    death_lunar_day = Column(Integer)
    death_lunar_leap = Column(Boolean, default=False)
    alive = Column(Boolean)
    life_status = Column(String(16))  # unknown/alive/deceased; NULL preserves legacy uncertainty
    status = Column(String(16))  # pending/doing/drafted/verified
    notes = Column(JSON)
    sort = Column(Numeric(10, 0), nullable=False, default=0)
    user_id = Column(String(64), index=True)  # 关联的登录用户 id（"这是我"认领）；一个用户在一个家庭只关联一个人物
    gender = Column(String(8))  # M=男 F=女 空=未知；用于按登录者自动计算称谓
    spouse_id = Column(String(64))  # 配偶的人物 id（双向）；称谓计算时夫妻视为同一辈分单元

    @property
    def life_state(self):
        if self.life_status in ("unknown", "alive", "deceased"):
            return self.life_status
        if self.alive is True:
            return "alive"
        if self.death_date_label:
            return "deceased"
        return "unknown"

    @staticmethod
    def _cal_label(year, calendar):
        """年份显示：农历加前缀，公历不加。"""
        if not year:
            return ""
        return ("农历" if calendar == "lunar" else "") + str(year)

    @property
    def birth_label(self):
        return self._cal_label(self.birth_year, self.birth_calendar)

    @property
    def death_label(self):
        return self._cal_label(self.death_year, self.death_calendar)

    @property
    def birth_date_label(self):
        from person_dates import date_label
        return date_label(self, 'birth')

    @property
    def death_date_label(self):
        from person_dates import date_label
        return date_label(self, 'death')


class SourceFile(AuditMixin, Base):
    __tablename__ = "source_files"
    family_id = Column(String(64), index=True)
    uploader_id = Column(String(64))
    file_name = Column(String(255))
    file_type = Column(String(16))  # audio/video/text
    file_size = Column(BigInteger)
    duration_sec = Column(Integer)
    storage_path = Column(String(512))
    file_hash = Column(String(64), index=True)


class Transcript(AuditMixin, Base):
    __tablename__ = "transcripts"
    source_file_id = Column(String(64), index=True)
    version = Column(Integer)
    content = Column(Text)
    asr_engine = Column(String(64))
    confidence = Column(Numeric(5, 4))


class Interview(AuditMixin, Base):
    __tablename__ = "interviews"
    family_id = Column(String(64), index=True)
    source_file_id = Column(String(64))
    transcript_id = Column(String(64))
    person_id = Column(String(64))
    topic = Column(String(128))
    prompt_version = Column(String(32))
    llm_model = Column(String(64))
    status = Column(String(16))  # processing/done/failed
    view_count = Column(Integer, default=0)  # 观看数
    like_count = Column(Integer, default=0)  # 点赞数
    period_start = Column(Date)  # 故事时间段起
    period_end = Column(Date)  # 故事时间段止
    period_precision = Column(String(8))  # year/month/day，精度不足时起止取当年1月1日/当年12月31日
    author_id = Column(String(64))  # 作者用户 id（用户手写文章；AI整理的可空）
    published_at = Column(DateTime, index=True)  # first publication only; NULL means legacy estimate
    publish_status = Column(String(16), default="draft")  # draft=草稿 published=已发布；NULL 视为已发布（兼容旧数据）
    visibility = Column(String(16), default="public")  # public=家庭可见 private=仅作者 specific=指定人；NULL 视为 public
    narrator_person_id = Column(String(64), index=True)  # 讲述者（树上人物 id；skill"讲述者确认"规则对应，对应不上时空）

    @property
    def publication_time(self):
        return self.published_at or self.create_date

    @property
    def publication_time_inferred(self):
        return self.published_at is None


class Draft(AuditMixin, Base):
    __tablename__ = "drafts"
    interview_id = Column(String(64), index=True)
    version = Column(Integer)
    content = Column(Text)
    search_text = Column(Text().with_variant(MEDIUMTEXT(), 'mysql'))
    is_current = Column(Boolean, default=False)
    voice_authorized_by = Column(String(64))
    voice_authorized_at = Column(DateTime)
    voice_authorized_hash = Column(String(64))


@event.listens_for(Draft,'before_insert')
@event.listens_for(Draft,'before_update')
def normalize_draft_search(mapper,connection,target):
    from search_index import plain_text
    target.search_text=plain_text(target.content)


class VoiceProfile(AuditMixin, Base):
    __tablename__ = 'voice_profiles'
    family_id = Column(String(64), nullable=False, index=True)
    person_id = Column(String(64), nullable=False, unique=True)
    epoch = Column(Integer, nullable=False, default=1)
    provider = Column(String(24), nullable=False, default='cosyvoice')
    workspace_id = Column(String(80), nullable=False, default='')
    model = Column(String(64), nullable=False)
    prefix = Column(String(10), nullable=False, unique=True)
    status = Column(String(24), nullable=False, default='consent')
    subject_state = Column(String(16), nullable=False)
    subject_user_id = Column(String(64))
    reviewed_by = Column(String(64))
    reviewed_at = Column(DateTime)
    evidence_ref = Column(String(80))
    sample_key = Column(String(255))
    provider_voice_id = Column(String(255))
    uncertain = Column(Boolean, nullable=False, default=False)
    lease_token = Column(String(64))
    lease_until = Column(DateTime)
    error_code = Column(String(32))


class VoiceConsent(AuditMixin, Base):
    __tablename__ = 'voice_consents'
    profile_id = Column(String(64), nullable=False, index=True)
    epoch = Column(Integer, nullable=False)
    user_id = Column(String(64), nullable=False)
    relation = Column(String(32), nullable=False)
    version = Column(String(32), nullable=False)
    revoked_at = Column(DateTime)
    __table_args__ = (UniqueConstraint('profile_id','epoch','user_id',name='uq_voice_consent'),)


class VoiceAudio(AuditMixin, Base):
    __tablename__ = 'voice_audio'
    family_id = Column(String(64), nullable=False, index=True)
    profile_id = Column(String(64), nullable=False, index=True)
    epoch = Column(Integer, nullable=False)
    interview_id = Column(String(64), nullable=False, index=True)
    draft_id = Column(String(64), nullable=False)
    text_hash = Column(String(64), nullable=False)
    requested_by = Column(String(64), nullable=False)
    status = Column(String(24), nullable=False, default='queued')
    storage_key = Column(String(255))
    charge_id = Column(String(64))
    lease_token = Column(String(64))
    lease_until = Column(DateTime)
    error_code = Column(String(32))


class VoiceCharge(AuditMixin, Base):
    """Conservative reservations, not the provider's settled bill; failed attempts are retained."""
    __tablename__ = 'voice_charges'
    family_id = Column(String(64), nullable=False, index=True)
    audio_id = Column(String(64), nullable=False, index=True)
    period = Column(String(7), nullable=False)
    characters = Column(Integer, nullable=False)
    status = Column(String(24), nullable=False, default='reserved')


class VoiceAudit(AuditMixin, Base):
    __tablename__ = 'voice_audit'
    profile_id = Column(String(64), nullable=False, index=True)
    action = Column(String(32), nullable=False)
    epoch = Column(Integer, nullable=False)


class Quote(AuditMixin, Base):
    __tablename__ = "quotes"
    interview_id = Column(String(64), index=True)
    text = Column(String(512))
    status = Column(String(16))  # pending/kept/dropped


class VerificationItem(AuditMixin, Base):
    __tablename__ = "verification_items"
    interview_id = Column(String(64), index=True)
    text = Column(String(512))
    reason = Column(String(512))
    person_id = Column(String(64))
    status = Column(String(16))  # pending/resolved
    correction = Column(String(512))
    resolved_at = Column(DateTime)


@event.listens_for(VerificationItem,'before_insert')
@event.listens_for(VerificationItem,'before_update')
def mark_verification_resolution(mapper,connection,target):
    if not inspect(target).attrs.status.history.has_changes():return
    from reporting import local_now
    target.resolved_at=local_now() if target.status=='resolved' else None


class PersonLink(AuditMixin, Base):
    __tablename__ = "person_links"
    interview_id = Column(String(64), index=True)
    mention = Column(String(64))
    person_id = Column(String(64))
    is_new = Column(Boolean, default=False)
    status = Column(String(16))  # linked/pending_confirm


class NewPerson(AuditMixin, Base):
    __tablename__ = "new_persons"
    family_id = Column(String(64), index=True)
    interview_id = Column(String(64))
    name = Column(String(64))
    context = Column(String(512))
    join_tree = Column(String(16))  # pending/joined/dismissed


class TimelineEvent(AuditMixin, Base):
    __tablename__ = "timeline_events"
    family_id = Column(String(64), index=True)
    person_id = Column(String(64), index=True)
    event_date = Column(Date)
    date_precision = Column(String(8))  # year/month/day
    title = Column(String(128))
    description = Column(Text)
    source_interview_id = Column(String(64))


class Photo(AuditMixin, Base):
    __tablename__ = "photos"
    family_id = Column(String(64))
    person_id = Column(String(64), index=True)
    photo_year = Column(Integer)
    event_id = Column(String(64))
    storage_path = Column(String(512))
    caption = Column(String(255))
    uploaded_by = Column(String(64))


class Portrait(AuditMixin, Base):
    __tablename__ = "portraits"
    person_id = Column(String(64), index=True)
    version = Column(Integer)
    profile_text = Column(Text)
    generated_image_path = Column(String(512))  # v2


class ShareSnapshot(AuditMixin, Base):
    __tablename__ = "share_snapshots"
    family_id = Column(String(64), index=True)
    title = Column(String(128))
    content_json = Column(JSON)
    token = Column(String(64), unique=True)
    password_hash = Column(String(128))
    status = Column(String(16), default="draft")  # draft 待确认 / published 已发布
    expires_at = Column(DateTime)


class Comment(AuditMixin, Base):
    """评论（树形，parent_id 挂靠，参考 persons/sys_area 模式）。"""
    __tablename__ = "comments"
    interview_id = Column(String(64), index=True)
    user_id = Column(String(64), index=True)
    parent_id = Column(String(64), nullable=False, default="0")  # 0=顶层，否则为父评论 id
    content = Column(Text, nullable=False)
    like_count = Column(Integer, default=0)


class Like(AuditMixin, Base):
    """点赞明细（target_type: interview / comment），一人一目标一条。"""
    __tablename__ = "likes"
    target_type = Column(String(16))
    target_id = Column(String(64), index=True)
    user_id = Column(String(64), index=True)


class InterviewViewer(AuditMixin, Base):
    """故事指定可见人：visibility=specific 时的白名单。"""
    __tablename__ = "interview_viewers"
    interview_id = Column(String(64), index=True)
    user_id = Column(String(64), index=True)


class InterviewPerson(AuditMixin, Base):
    """故事关联人物（多对多）：讲述对象 + 相关人物，用于人物线串联。"""
    __tablename__ = "interview_persons"
    interview_id = Column(String(64), index=True)
    person_id = Column(String(64), index=True)
    role = Column(String(16))  # subject=讲述对象，related=关联人物


_engine = None
_Session = None


def init_db(database_url: str, *, pool_recycle_seconds: int = 1800):
    """Configure worker connections only; schema changes run once before startup."""
    global _engine, _Session
    if pool_recycle_seconds < 1:
        raise ValueError("DB_POOL_RECYCLE_SECONDS 必须为正整数")
    engine_options = {"pool_pre_ping": True}
    # MySQL drops idle connections. Never age-recycle an in-memory SQLite DB.
    if make_url(database_url).get_backend_name() == "mysql":
        engine_options["pool_recycle"] = pool_recycle_seconds
    if _Session is not None:
        _Session.remove()
    if _engine is not None:
        _engine.dispose()
    _engine = create_engine(database_url, **engine_options)
    _Session = scoped_session(sessionmaker(bind=_engine))


def get_session():
    return _Session()


def remove_session():
    if _Session is not None:
        _Session.remove()


class SyncLog(AuditMixin, Base):
    """同步日志：每次 sync-json 入库一条；client_id 唯一，用于幂等去重。"""
    __tablename__ = "sync_log"
    family_id = Column(String(64), index=True)
    op_type = Column(String(32))  # tree_upsert/interview_upsert/...
    client_id = Column(String(64), unique=True)
    target_id = Column(String(64))  # 落库的主记录 id（如 interview_id）
    status = Column(String(16), default="ok")  # ok/skipped/failed
    summary = Column(String(512))


class PersonIdMap(AuditMixin, Base):
    """skill 侧人物 id → 本站 person_id 的映射（tree_upsert 建立）。"""
    __tablename__ = "person_id_map"
    family_id = Column(String(64), index=True)
    skill_id = Column(String(64))
    person_id = Column(String(64))
    __table_args__ = (
        UniqueConstraint("family_id", "skill_id", name="uq_map_family_skill"),
    )


class AiMemory(AuditMixin, Base):
    """AI 按用户保留的记忆：身份、偏好、进行中的事，用于针对性服务。"""
    __tablename__ = "ai_memories"
    family_id = Column(String(64), index=True)
    user_id = Column(String(64), index=True)
    memory_key = Column(String(32), default="profile")  # profile 画像/偏好
    content = Column(Text)
    __table_args__ = (
        UniqueConstraint("family_id", "user_id", "memory_key",
                         name="uq_ai_mem"),
    )


class AiPreference(AuditMixin, Base):
    """Per-user/family reset boundary, locked when publishing derived AI state."""
    __tablename__ = 'ai_preferences'
    family_id = Column(String(64), nullable=False)
    user_id = Column(String(64), nullable=False)
    epoch = Column(String(32), nullable=False, default='legacy')
    __table_args__ = (UniqueConstraint('family_id','user_id',name='uq_ai_preference'),)


class FamilyVisit(AuditMixin, Base):
    __tablename__ = 'family_visits'
    family_id = Column(String(64), nullable=False)
    user_id = Column(String(64), nullable=False)
    first_seen_at = Column(DateTime, nullable=False)
    first_read_at = Column(DateTime)
    first_saved_at = Column(DateTime)
    first_published_at = Column(DateTime)
    guide_status = Column(String(16), nullable=False, default='auto')
    cohort_eligible = Column(Boolean, nullable=False, default=False)
    __table_args__ = (UniqueConstraint('family_id','user_id',name='uq_family_visit'),)


class PrivacyRequest(AuditMixin, Base):
    __tablename__ = 'privacy_requests'
    user_id = Column(String(64), nullable=False, index=True)
    kind = Column(String(24), nullable=False)
    details = Column(Text, nullable=False)
    status = Column(String(16), nullable=False, default='submitted')
    revision = Column(Integer, nullable=False, default=1)
    first_response_at = Column(DateTime)
    identity_verified_at = Column(DateTime)
    resolved_at = Column(DateTime)


class PrivacyResponse(AuditMixin, Base):
    __tablename__ = 'privacy_responses'
    request_id = Column(String(64), nullable=False, index=True)
    actor_role = Column(String(16), nullable=False)
    revision = Column(Integer, nullable=False)
    status = Column(String(16), nullable=False)
    content = Column(Text, nullable=False)
    __table_args__ = (UniqueConstraint('request_id','revision',name='uq_privacy_response_revision'),)


class UsageEvent(AuditMixin, Base):
    __tablename__ = 'usage_events'
    family_id = Column(String(64), nullable=False, index=True)
    user_id = Column(String(64), nullable=False, index=True)
    kind = Column(String(16), nullable=False)
    outcome = Column(String(16), nullable=False)
    duration_ms = Column(Integer, nullable=False)
    __table_args__ = (Index('ix_usage_actor_time','user_id','family_id','create_date'),
                      Index('ix_usage_events_create_date','create_date'))


class StoryPublication(AuditMixin, Base):
    """Immutable first publication evidence; id is the story id, no body is copied."""
    __tablename__ = 'story_publications'
    family_id = Column(String(64), nullable=False, index=True)
    user_id = Column(String(64))
    published_at = Column(DateTime, nullable=False, index=True)


@event.listens_for(Interview,'after_insert')
@event.listens_for(Interview,'after_update')
def record_first_publication(mapper,connection,target):
    if not target.published_at or not target.family_id:return
    from reporting import local_now
    values=dict(id=target.id,family_id=target.family_id,user_id=target.author_id,published_at=target.published_at,
                create_date=local_now(),create_by=target.update_by or target.create_by,del_flag=0)
    if connection.dialect.name=='mysql':
        from sqlalchemy.dialects.mysql import insert
        statement=insert(StoryPublication.__table__).values(**values)
        statement=statement.on_duplicate_key_update(id=statement.inserted.id)
    else:
        from sqlalchemy.dialects.sqlite import insert
        statement=insert(StoryPublication.__table__).values(**values).on_conflict_do_nothing(index_elements=['id'])
    connection.execute(statement)


class MetricSample(AuditMixin, Base):
    __tablename__ = 'metric_samples'
    year = Column(Integer, nullable=False)
    week = Column(Integer, nullable=False)
    kind = Column(String(24), nullable=False)
    task = Column(String(24), nullable=False, default='')
    device = Column(String(80))
    evidence_ref = Column(String(80), nullable=False)
    sample_count = Column(Integer, nullable=False)
    success_count = Column(Integer, nullable=False)
    assisted_success = Column(Integer, nullable=False, default=0)
    void_reason = Column(String(32))
    __table_args__ = (UniqueConstraint('year','week','kind','task','evidence_ref',name='uq_metric_evidence'),)


class AiMessage(AuditMixin, Base):
    """AI 问答聊天记录。"""
    __tablename__ = "ai_messages"
    family_id = Column(String(64), index=True)
    user_id = Column(String(64), index=True)
    role = Column(String(16))  # user / assistant
    content = Column(Text)


class AiCache(AuditMixin, Base):
    """AI 生成结果缓存（如周报导读），key 唯一，生成一次重复用。"""
    __tablename__ = "ai_cache"
    family_id = Column(String(64), index=True)
    cache_key = Column(String(128), unique=True)  # 如 weekly:wang:2026:42
    content = Column(Text)


class WritingPlan(AuditMixin, Base):
    """写作/采访计划：管理员定优先级（先写谁），skill 拉取后按计划引导用户。"""
    __tablename__ = "writing_plans"
    family_id = Column(String(64), index=True)
    title = Column(String(128))
    status = Column(String(16), default="draft")  # draft 草稿 / active 当前 / archived 归档
    items = Column(Text)  # JSON: [{person_id, person_name, order, status, note, reason}]


class SmsCode(AuditMixin, Base):
    """短信验证码：注册 / 找回密码。"""
    __tablename__ = "sms_codes"
    phone = Column(String(20), index=True)
    code = Column(String(10))
    purpose = Column(String(16))  # register / reset
    used = Column(Integer, default=0)
    expire_at = Column(DateTime)


class Invite(AuditMixin, Base):
    """家庭邀请码：被邀请人注册/登录后自动入家庭。"""
    __tablename__ = "invites"
    family_id = Column(String(64), index=True)
    code = Column(String(16), unique=True)
    max_uses = Column(Integer, default=0)  # 0=不限次数
    used_count = Column(Integer, default=0)
    expire_at = Column(DateTime)


class LegalAcceptance(AuditMixin, Base):
    """Self-registration acknowledgement; never inferred for existing or provisioned users."""
    __tablename__ = "legal_acceptances"
    user_id = Column(String(64), nullable=False)
    terms_version = Column(String(32), nullable=False)
    privacy_version = Column(String(32), nullable=False)
    accepted_at = Column(DateTime, nullable=False)  # UTC


class StoryCorrection(AuditMixin, Base):
    """A reader's suggestion is applied only alongside a reviewed new story version."""
    __tablename__ = 'story_corrections'
    interview_id = Column(String(64), nullable=False, index=True)
    user_id = Column(String(64), nullable=False)
    verification_id = Column(String(64))
    proposal = Column(Text, nullable=False)
    evidence = Column(Text)
    status = Column(String(16), default='pending')
    decision = Column(String(255))
    reviewed_by = Column(String(64))
    reviewed_at = Column(DateTime)


class AiTurn(AuditMixin, Base):
    """An idempotent, user-owned AI attempt; failures retain the original question."""
    __tablename__ = 'ai_turns'
    family_id = Column(String(64), nullable=False, index=True)
    user_id = Column(String(64), nullable=False, index=True)
    question = Column(Text, nullable=False)
    logical_id = Column(String(64), index=True)
    answer = Column(Text)
    status = Column(String(16), nullable=False)
    error = Column(String(255))
    sources = Column(JSON)
    context_stamp = Column(String(64), nullable=False)
    lease_until = Column(DateTime)
