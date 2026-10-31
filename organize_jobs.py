"""Durable generation attempts. Unknown external outcomes are never auto-replayed."""
import datetime
import hashlib
import re
from uuid import uuid4

from flask import abort, current_app
from sqlalchemy import func

from models import OrganizeRecord, OrganizeSource, OrganizeTask, User, get_session
from organizing import owned, member
from reporting import local_now

ACTIVE = ('queued', 'running')
MESSAGES = {'queued': '已排队，原稿已保存。', 'running': '正在整理，可离开页面后回来查看。',
 'succeeded': '整理完成，请核对内容。', 'failed': '本次整理未完成，原稿保留，可核对后重新生成。',
 'uncertain': '连接已中断，服务用量结果不确定；不会自动重做，请先核对后再决定。',
 'cancelled': '已停止本站后续处理；已发出的请求可能已经产生用量。', 'outdated': '原稿、身份或访问范围已变化，请重新核对。'}


def enabled():
    c = current_app.config
    return bool(c.get('ORGANIZE_ENABLED') and c.get('INAPP_AI_DATA_APPROVED') and c.get('DEEPSEEK_API_KEY'))


def begin(family_id, user_id, record_id, revision, nonce, consent=False, regenerate=False):
    s = get_session()
    record = owned(s, family_id, user_id, record_id, lock=True)
    if not re.fullmatch(r'[A-Za-z0-9_-]{8,80}', nonce or ''):
        abort(400, '请求编号无效，请刷新后重试。')
    identifier = hashlib.sha256((user_id+'\0'+record.id+'\0'+nonce).encode()).hexdigest()
    prior = s.get(OrganizeTask, identifier)
    if prior:
        if prior.input_revision != int(revision):
            abort(409, '该请求编号用于另一版本，请刷新核对。')
        return prior
    if record.story_id or str(record.revision) != str(revision):
        abort(409, '原稿已更新或已成稿，请重新打开记录核对。')
    if not consent or not enabled():
        abort(400, '请先确认将本原稿交由 AI 整理；未开通时仍可保存和导出原稿。')
    s.query(User).filter_by(id=user_id, del_flag=0).with_for_update().one()
    existing = s.query(OrganizeTask).filter_by(record_id=record.id, input_revision=record.revision).filter(
        OrganizeTask.status.in_(ACTIVE + (() if regenerate else ('succeeded',)))).order_by(OrganizeTask.create_date.desc()).with_for_update().populate_existing().first()
    if existing:
        return existing
    start = local_now().replace(hour=0, minute=0, second=0, microsecond=0)
    q = s.query(OrganizeTask).filter(OrganizeTask.user_id == user_id, OrganizeTask.create_date >= start)
    charged = q.with_entities(OrganizeTask.id, OrganizeTask.source_chars).with_for_update().all()
    if len(charged) >= current_app.config['ORGANIZE_DAILY_TASKS'] or sum(row.source_chars for row in charged) + len(record.content) > current_app.config['ORGANIZE_DAILY_CHARS']:
        abort(429, '今日整理额度已用完；原稿仍可保存、编辑或导出。')
    task = OrganizeTask(id=identifier, family_id=family_id, user_id=user_id, record_id=record.id,
        input_revision=record.revision, source_chars=len(record.content), status='queued',
        model=current_app.config['ORGANIZE_MODEL'], prompt_version='organize-v1', create_by=user_id,
        create_date=local_now())
    s.add(task)
    s.commit()
    return task


def cancel(family_id, user_id, record_id, task_id):
    s = get_session()
    owned(s, family_id, user_id, record_id)
    s.query(OrganizeTask).filter_by(id=task_id, record_id=record_id, user_id=user_id).filter(
        OrganizeTask.status.in_(ACTIVE)).update({OrganizeTask.status: 'cancelled'}, synchronize_session=False)
    s.commit()


def run_one(provider=None):
    s = get_session()
    now = local_now()
    s.query(OrganizeTask).filter(OrganizeTask.status == 'running', OrganizeTask.lease_until < now).update(
        {OrganizeTask.status: 'uncertain', OrganizeTask.error_code: 'lease_expired'}, synchronize_session=False)
    s.commit()
    if not enabled():
        return False
    task = s.query(OrganizeTask).filter_by(status='queued').order_by(OrganizeTask.create_date, OrganizeTask.id).with_for_update().first()
    if not task:
        return False
    identifier, token = task.id, uuid4().hex
    changed = s.query(OrganizeTask).filter_by(id=identifier, status='queued').update({
        OrganizeTask.status: 'running', OrganizeTask.lease_token: token,
        OrganizeTask.lease_until: now + datetime.timedelta(minutes=6)}, synchronize_session=False)
    if not changed:
        s.rollback()
        return False
    s.commit()
    try:
        s.expire_all()
        task = s.get(OrganizeTask, identifier)
        record = owned(s, task.family_id, task.user_id, task.record_id)
        if record.revision != task.input_revision or record.story_id:
            raise Outdated()
        source = s.query(OrganizeSource).filter_by(record_id=record.id, revision=task.input_revision).one()
        payload = dict(content=source.content, identity=source.identity, family_id=task.family_id,
                       user_id=task.user_id, model=task.model, prompt_version=task.prompt_version)
        s.commit()
        if provider is None:
            from organize_provider import generate
            provider = generate
        result, usage = provider(payload)
        s.rollback()
        s.expire_all()
        task = s.query(OrganizeTask).filter_by(id=identifier).with_for_update().populate_existing().one()
        if task.status != 'running' or task.lease_token != token:
            s.rollback()
            return True
        record = owned(s, task.family_id, task.user_id, task.record_id, lock=True)
        if record.revision != task.input_revision or record.story_id:
            raise Outdated()
        task.result, task.usage, task.status = result, usage, 'succeeded'
        s.commit()
    except Exception as exc:
        s.rollback()
        status = 'outdated' if isinstance(exc, Outdated) or getattr(exc, 'code', None) == 404 else ('uncertain' if getattr(exc, 'uncertain', False) else 'failed')
        s.query(OrganizeTask).filter_by(id=identifier, status='running', lease_token=token).update({
            OrganizeTask.status: status, OrganizeTask.error_code: 'request_unfinished' if status == 'uncertain' else 'result_unavailable'}, synchronize_session=False)
        s.commit()
    return True


class Outdated(Exception):
    pass
