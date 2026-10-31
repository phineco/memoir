"""One atomic draft per private material. Publishing remains an explicit story action."""
import calendar
import datetime
import hashlib
import html
import re

from flask import abort
from sqlalchemy.exc import IntegrityError

from models import (Draft, Interview, InterviewPerson, OrganizeRecord, OrganizeTask,
                    Person, Quote, TimelineEvent, VerificationItem, new_id)
from organizing import owned
from reporting import local_now


def confirm(s, fid, uid, rid, source_revision, preview_revision, nonce, related_ids=()):
    if not re.fullmatch(r'[A-Za-z0-9_-]{8,80}', nonce or ''):
        abort(400, '请刷新页面后确认。')
    record = owned(s, fid, uid, rid, lock=True)
    if record.story_id:
        story = s.query(Interview).filter_by(id=record.story_id, family_id=fid, author_id=uid, del_flag=0).first()
        if not story: abort(409, '关联故事已删除或状态变化，请先核对记录。')
        return story
    if str(record.revision) != str(source_revision) or str(record.preview_revision) != str(preview_revision) or not record.preview or record.preview_source_revision != record.revision:
        abort(409, '原稿或预览已变化，请重新核对，未创建故事。')
    related_ids = set(related_ids)
    required_ids = related_ids | {p for p in (record.narrator_id, record.subject_id) if p}
    allowed = {p[0] for p in s.query(Person.id).filter(Person.family_id == fid, Person.del_flag == 0, Person.id.in_(required_ids)).all()}
    if required_ids != allowed:
        abort(400, '人物已删除或不属于当前家庭；请先更新讲述身份。')
    sid = hashlib.sha256(('organize-story\0'+record.id).encode()).hexdigest()
    changed = s.query(OrganizeRecord).filter_by(id=record.id, revision=record.revision,
        preview_revision=record.preview_revision, story_id=None).update({OrganizeRecord.story_id: sid}, synchronize_session=False)
    if changed != 1:
        s.rollback()
        abort(409, '另一窗口刚刚保存，请重新打开记录查看。')
    data = record.preview
    task = s.query(OrganizeTask).filter_by(record_id=rid, input_revision=record.revision, status='succeeded').order_by(OrganizeTask.create_date.desc()).first()
    story = Interview(id=sid, family_id=fid, author_id=uid, person_id=record.subject_id,
        narrator_person_id=record.narrator_id, topic=data['title'], status='done',
        publish_status='draft', visibility='private', create_by=uid, create_date=local_now(),
        llm_model=task.model if task else None, prompt_version=task.prompt_version if task else 'manual-v1',
        remarks=('讲述称谓：'+record.narrator_label) if record.narrator_label else None)
    if data.get('period'):
        period = data['period']; precision = period['precision']
        story.period_start = parse_date(period['start'], precision)
        story.period_end = parse_date(period['end'], precision, end=True)
        story.period_precision = precision
    body = data['body']
    for row in data['quotes']:
        if row.get('kind') == 'summary': body += '\n\n摘要（人工整理）：'+row['text']
    content = ''.join('<p>'+html.escape(p).replace('\n','<br>')+'</p>' for p in body.split('\n\n') if p.strip())
    s.add(story)
    s.add(Draft(id=new_id(), interview_id=sid, version=1, is_current=True, content=content, create_by=uid))
    saved = {'quotes': [], 'verification': [], 'timeline': []}
    for row in data['quotes']:
        if row.get('kind') == 'summary': continue
        # Revalidate original words at the final write boundary.
        if row['text'] not in record.content: abort(409, '原话依据已变化，请重新核对。')
        item = Quote(id=new_id(), interview_id=sid, text=row['text'], status='kept', create_by=uid)
        s.add(item); saved['quotes'].append(item.id)
    for row in data['verification']:
        item = VerificationItem(id=new_id(), interview_id=sid, text=row['text'], reason='原稿依据：'+row['evidence'][:480], status='pending', create_by=uid)
        s.add(item); saved['verification'].append(item.id)
    for row in data['timeline']:
        item = TimelineEvent(id=new_id(), family_id=fid, source_interview_id=sid, person_id=record.subject_id,
            event_date=parse_date(row['date'], row['precision']), date_precision=row['precision'], title=row['title'],
            description='原稿依据：'+row['evidence'], create_by=uid)
        s.add(item); saved['timeline'].append(item.id)
    if record.subject_id:
        s.add(InterviewPerson(id=new_id(), interview_id=sid, person_id=record.subject_id, role='subject', create_by=uid))
    for pid in sorted(related_ids - {record.subject_id}):
        s.add(InterviewPerson(id=new_id(), interview_id=sid, person_id=pid, role='related', create_by=uid))
    record.preview = dict(data, saved_items=saved)
    record.story_id = sid
    try:
        s.flush()
        from onboarding import record as note_saved
        note_saved(fid, uid, 'saved')
        s.commit()
    except IntegrityError:
        s.rollback()
        old = owned(s, fid, uid, rid)
        if old.story_id == sid:
            return s.query(Interview).filter_by(id=sid, author_id=uid, del_flag=0).one()
        raise
    except Exception:
        s.rollback()
        raise
    return story


def parse_date(value, precision, end=False):
    date = datetime.date.fromisoformat(value + {'year': '-01-01', 'month': '-01', 'day': ''}[precision])
    if end and precision == 'year': return datetime.date(date.year, 12, 31)
    if end and precision == 'month': return datetime.date(date.year, date.month, calendar.monthrange(date.year, date.month)[1])
    return date
