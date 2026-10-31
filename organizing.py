"""User-owned source materials. AI previews never imply publishing permission."""
import hashlib
import re

from flask import abort
from sqlalchemy.exc import IntegrityError

from access import family_role
from models import OrganizeRecord, OrganizeSource, Person, User, new_id
from reporting import local_now

MAX_TEXT = 20000
MAX_FILE = 1024 * 1024


def member(s, family_id, user_id):
    if not s.query(User.id).filter_by(id=user_id, del_flag=0).first() or not family_role(s, family_id, user_id):
        abort(404)


def owned(s, family_id, user_id, record_id, lock=False):
    if lock:
        from transaction_locks import serialize_sqlite
        serialize_sqlite(s,user_id)
    member(s, family_id, user_id)
    q = s.query(OrganizeRecord).filter_by(id=record_id, family_id=family_id, user_id=user_id, del_flag=0)
    record = (q.with_for_update() if lock else q).populate_existing().first()
    if not record:
        abort(404)
    return record


def fields(s, family_id, data):
    content = data.get('content', '')
    if not isinstance(content, str) or not content.strip() or len(content) > MAX_TEXT:
        abort(400, '请填写原稿，最多 20000 字；超出时请拆分，不会自动截断。')
    topic = data.get('topic', '').strip()
    label = data.get('narrator_label', '').strip()
    if len(topic) > 128 or len(label) > 100:
        abort(400, '标题或讲述称谓过长')
    mode = data.get('recording_mode', 'unspecified')
    if mode not in ('self', 'accompany', 'unspecified'): abort(400, '请选择讲述方式')
    values = dict(content=content, topic=topic, narrator_label=label or None, recording_mode=mode)
    for name in ('narrator_id', 'subject_id'):
        value = data.get(name) or None
        if value and (not isinstance(value, str) or not s.query(Person.id).filter_by(id=value, family_id=family_id, del_flag=0).first()):
            abort(400, '人物必须属于当前家庭；身份不明可以暂不选择。')
        values[name] = value
    return values


def snapshot(s, record):
    s.add(OrganizeSource(id=new_id(), record_id=record.id, revision=record.revision,
                        content=record.content, identity={name: getattr(record, name) for name in
                        ('topic', 'narrator_id', 'subject_id', 'narrator_label', 'recording_mode')}, create_by=record.user_id))


def create(s, family_id, user_id, data, nonce=None):
    member(s, family_id, user_id)
    values = fields(s, family_id, data)
    if nonce is not None and (not isinstance(nonce, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,80}', nonce)):
        abort(400, '请刷新页面后重试')
    identifier = hashlib.sha256((family_id+'\0'+user_id+'\0'+nonce).encode()).hexdigest() if nonce else new_id()
    def prior():
        record = s.get(OrganizeRecord, identifier)
        if record and any(getattr(record, key) != value for key, value in values.items()):
            abort(409, '该保存编号已有不同内容，请重新打开新原稿页面。')
        return record
    existing = prior()
    if existing:
        return existing
    record = OrganizeRecord(id=identifier, family_id=family_id, user_id=user_id,
                            revision=1, preview_revision=0, create_by=user_id,
                            **values)
    s.add(record)
    snapshot(s, record)
    try:
        s.commit()
    except IntegrityError:
        s.rollback()
        existing = prior()
        if not existing:
            raise
        return existing
    return record


def update(s, family_id, user_id, record_id, revision, data):
    record = owned(s, family_id, user_id, record_id, lock=True)
    if record.story_id:
        abort(409, '已生成正式草稿，请进入故事修订；不能从原记录重复建稿。')
    if str(record.revision) != str(revision):
        abort(409, '原稿已更新，请刷新后核对，当前内容未覆盖。')
    values = fields(s, family_id, data)
    values.update(revision=record.revision + 1, update_date=local_now())
    changed = s.query(OrganizeRecord).filter_by(id=record.id, revision=record.revision).update(values, synchronize_session=False)
    if changed != 1:
        s.rollback()
        abort(409, '原稿刚刚被其他窗口更新，请核对后重试。')
    s.refresh(record)
    snapshot(s, record)
    s.commit()
    return record


def delete(s, family_id, user_id, record_id, acknowledge_story=False, commit=True):
    record = owned(s, family_id, user_id, record_id, lock=True)
    if record.story_id and not acknowledge_story:
        abort(409, '已有正式故事。删除原材料不会删除故事，请先明确确认。')
    from models import OrganizeTask
    s.query(OrganizeTask).filter_by(record_id=record.id).update({
        OrganizeTask.status: 'cancelled', OrganizeTask.result: None, OrganizeTask.usage: None}, synchronize_session=False)
    s.query(OrganizeSource).filter_by(record_id=record.id).delete(synchronize_session=False)
    s.delete(record)
    if commit:s.commit()
