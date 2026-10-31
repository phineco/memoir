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
    if lock:
        from transaction_locks import serialize_sqlite
        serialize_sqlite(s,uid)
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
        state='active', revision=1, followups=0, ai_consent=data.get('ai_consent')=='yes', create_by=uid, **values)
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
    cancel_questions(s, row)
    claim(s, row, state='active' if resume else 'paused')
    s.commit(); return row


def answers(s, sid):
    return s.query(InterviewAnswer).filter_by(session_id=sid, del_flag=0).order_by(InterviewAnswer.sequence).all()


FOLLOWUPS = ('那件事里，您最记得的一个细节是什么？', '回头看，这段经历给您留下了什么？')


def pending(s, row):
    from models import InterviewQuestion
    return s.query(InterviewQuestion).filter_by(session_id=row.id, input_revision=row.revision).filter(
        InterviewQuestion.status.in_(('queued','running'))).first()


def cancel_questions(s, row):
    from models import InterviewQuestion
    s.query(InterviewQuestion).filter_by(session_id=row.id).filter(InterviewQuestion.status.in_(('queued','running'))).update(
        {InterviewQuestion.status: 'cancelled'}, synchronize_session=False)


def answer(s, fid, uid, sid, revision, nonce, content, skip=False, clip_id=None):
    row = owned(s, fid, uid, sid, lock=True)
    aid = nonce_id('answer', sid, uid, nonce)
    prior = s.get(InterviewAnswer, aid)
    if prior:
        if prior.content != ('' if skip else content.strip()) or prior.kind != ('skip' if skip else 'text'):
            abort(409, '本次回答编号已有不同内容，请重新打开采访。')
        return row
    if str(row.revision) != str(revision): abort(409, '采访已更新，请先核对，当前回答未覆盖。')
    if row.state != 'active' or pending(s, row): abort(409, '请先继续采访，或等待下一个问题。')
    if not isinstance(content, str) or (not skip and (not content.strip() or len(content) > 4000)):
        abort(400, '回答可长可短，每段最多4000字；较长内容请分段。')
    clip=None
    if clip_id:
        from interview_audio import owned_clip
        clip=owned_clip(s,fid,uid,sid,clip_id)
        if clip.input_revision!=row.revision or clip.answer_id:abort(409,'录音对应的问题已变化，请保留转写后人工核对。')
    current = answers(s, sid)
    if len(current) >= 100 or sum(len(a.content)+len(a.question)+12 for a in current)+len(content)+len(row.question)+12 > 19000:
        abort(400, '本段材料已接近整理上限，请先结束本段并核对成稿，再开始下一段；当前回答未保存。')
    new_topic, followups = row.topic, row.followups + 1
    if skip or followups > 2:
        topics = list(TOPICS); new_topic = topics[(topics.index(row.topic)+1)%len(topics)]; followups = 0
    question = TOPICS[new_topic][1] if followups == 0 else FOLLOWUPS[followups-1]
    s.add(InterviewAnswer(id=aid, session_id=sid, sequence=len(current)+1, question=row.question,
        content='' if skip else content.strip(), kind='skip' if skip else 'text', version=1, history=[], create_by=uid))
    if clip:clip.answer_id=aid;clip.status='accepted'
    claim(s, row, question=question, topic=new_topic, followups=followups)
    from interview_questions import enqueue
    enqueue(s, row)
    s.commit(); return row


def switch_topic(s, fid, uid, sid, revision, topic):
    row = guard(s, fid, uid, sid, revision)
    if topic not in TOPICS or row.state == 'ended': abort(400, '请选择有效话题')
    cancel_questions(s, row)
    claim(s, row, topic=topic, followups=0, question=TOPICS[topic][1])
    s.commit(); return row


def use_template(s, fid, uid, sid, revision):
    row = guard(s, fid, uid, sid, revision)
    cancel_questions(s, row); claim(s, row)
    s.commit(); return row


def content(s, row):
    return '\n\n'.join('问：'+a.question+'\n答：'+a.content for a in answers(s,row.id) if a.kind != 'skip' and a.content.strip())


def finish(s, fid, uid, sid, revision):
    row = owned(s, fid, uid, sid, lock=True)
    if row.state == 'ended' and row.record_id: return row
    if str(row.revision) != str(revision): abort(409, '采访已更新，请重新核对。')
    source = content(s, row)
    if not source: abort(400, '请先保存至少一段回答；也可以暂停稍后再讲。')
    cancel_questions(s, row)
    from organizing import snapshot
    from models import OrganizeRecord
    rid = hashlib.sha256((fid+'\0'+uid+'\0interview-'+sid).encode()).hexdigest()
    record = s.get(OrganizeRecord,rid)
    if not record:
        record = OrganizeRecord(id=rid, family_id=fid, user_id=uid, content=source, topic='我的采访回忆',
            recording_mode=row.recording_mode, narrator_id=row.narrator_id, subject_id=row.subject_id,
            narrator_label=row.narrator_label, revision=1, preview_revision=0, create_by=uid)
        s.add(record); snapshot(s,record)
    claim(s, row, state='ended', record_id=record.id); s.commit(); return row


def edit_answer(s, fid, uid, sid, revision, answer_id, answer_version, value):
    row = guard(s, fid, uid, sid, revision)
    item = s.query(InterviewAnswer).filter_by(id=answer_id, session_id=sid, del_flag=0).first()
    if not item or str(item.version) != str(answer_version): abort(409, '回答已更新，请重新打开。')
    if not isinstance(value, str) or not value.strip() or len(value) > 4000: abort(400, '回答最多4000字，请分段。')
    from models import OrganizeRecord
    record = None
    if row.record_id:
        from organizing import owned as owned_record
        record = owned_record(s, fid, uid, row.record_id, lock=True)
        if record.story_id: abort(409, '本段已成稿，请到故事编辑保留正式修订；原始回答不覆盖。')
    if sum(len(a.content)+len(a.question)+12 for a in answers(s,sid))-len(item.content)+len(value) > 19000:
        abort(400, '修改后本段材料过长，请拆分，当前版本未覆盖。')
    item.history = list(item.history or []) + [{'version': item.version, 'content': item.content, 'kind': item.kind}]
    item.content = value.strip(); item.kind = 'text'; item.version += 1
    cancel_questions(s,row); claim(s,row)
    if record:
        from organizing import snapshot
        record.content = content(s,row); record.revision += 1; record.update_date = local_now(); snapshot(s,record)
    s.commit(); return row
