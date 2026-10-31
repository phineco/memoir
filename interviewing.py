"""Private, durable one-question interview sessions, independent of public AI memory."""
import hashlib
import re

from flask import abort
from sqlalchemy.exc import IntegrityError

from models import InterviewSession, InterviewAnswer, get_session
from organizing import member, fields
from reporting import local_now

TOPICS = {'childhood': ('童年', '小时候住的地方，您最记得什么？'),
          'family': ('家人', '您想先讲讲哪一位家人？'),
          'work': ('工作', '您第一次工作时，有什么难忘的事？'),
          'free': ('自由讲述', '今天最想讲哪一段回忆？')}


def nonce_id(prefix, fid, uid, nonce):
    if not re.fullmatch(r'[A-Za-z0-9_-]{8,80}', nonce or ''): abort(400, '请刷新后重试')
    return hashlib.sha256((prefix+'\0'+fid+'\0'+uid+'\0'+nonce).encode()).hexdigest()


def owned(s, fid, uid, sid, lock=False):
    member(s, fid, uid)
    q = s.query(InterviewSession).filter_by(id=sid, family_id=fid, user_id=uid, del_flag=0)
    row = (q.with_for_update() if lock else q).populate_existing().first()
    if not row: abort(404)
    return row


def start(s, fid, uid, data, nonce):
    member(s, fid, uid)
    topic = data.get('topic', 'childhood')
    if topic not in TOPICS: abort(400, '请选择采访话题')
    values = fields(s, fid, dict(data, content='身份核对', topic=''))
    values = {k: v for k, v in values.items() if k not in ('content', 'topic')}
    sid = nonce_id('interview', fid, uid, nonce)
    old = s.get(InterviewSession, sid)
    if old: return old
    row = InterviewSession(id=sid, family_id=fid, user_id=uid, topic=topic, question=TOPICS[topic][1],
        state='active', revision=1, followups=0, create_by=uid, **values)
    s.add(row)
    try: s.commit()
    except IntegrityError:
        s.rollback(); return owned(s, fid, uid, sid)
    return row


def guard(s, fid, uid, sid, revision):
    row = owned(s, fid, uid, sid, lock=True)
    if str(row.revision) != str(revision): abort(409, '采访已更新，请重新打开；已保存回答不会丢失。')
    return row


def claim(s, row, **values):
    values.update(revision=row.revision + 1, update_date=local_now())
    if s.query(InterviewSession).filter_by(id=row.id, revision=row.revision).update(values, synchronize_session=False) != 1:
        s.rollback(); abort(409, '另一窗口已更新采访，请重新核对。')
    s.refresh(row)


def pause(s, fid, uid, sid, revision, resume=False):
    row = guard(s, fid, uid, sid, revision)
    if row.state == 'ended': abort(409, '本段已结束，请查看整理记录或开始下一段采访。')
    claim(s, row, state='active' if resume else 'paused')
    s.commit(); return row


def answers(s, sid):
    return s.query(InterviewAnswer).filter_by(session_id=sid, del_flag=0).order_by(InterviewAnswer.sequence).all()
