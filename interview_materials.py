"""Private interview archive and durable object cleanup; stories are separate assets."""
import datetime
import hashlib
import json
import tempfile
import zipfile
from uuid import uuid4

from flask import abort
from sqlalchemy import or_, and_

import interviewing
import interview_audio
from models import (InterviewSession, InterviewAnswer, InterviewClip, InterviewQuestion,
                    InterviewAsrTask, OrganizeRecord, get_session)
from reporting import local_now


def export(s,fid,uid,sid):
    row=interviewing.owned(s,fid,uid,sid)
    clips=s.query(InterviewClip).filter_by(session_id=sid,del_flag=0).all()
    manifest={'format':1,'session':sid,'recording_mode':row.recording_mode,'narrator_label':row.narrator_label,
        'answers':[{'sequence':a.sequence,'question':a.question,'content':a.content,'version':a.version,'history':a.history} for a in interviewing.answers(s,sid)],
        'clips':[{'id':c.id,'question':c.question,'status':c.status,'duration_ms':c.duration_ms,'original_transcript':c.transcript,'answer_id':c.answer_id} for c in clips]}
    archive=tempfile.SpooledTemporaryFile(max_size=8*1024*1024,mode='w+b')
    try:
        total=0
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_STORED) as bundle:
            bundle.writestr('采访记录.json',json.dumps(manifest,ensure_ascii=False,indent=2))
            bundle.writestr('回答原稿.txt',interviewing.content(s,row))
            for clip in clips:
                if clip.status in ('uploading','upload_failed','deleting','deleted'):continue
                data=interview_audio.read(clip.storage_key);total+=len(data)
                if total>256*1024*1024:abort(413,'录音整包超过256MiB，请在页面逐段下载原声。')
                bundle.writestr('audio/'+clip.id+'.wav',data)
        archive.seek(0);return archive
    except Exception:archive.close();raise


def request_delete(s,fid,uid,sid):
    row=interviewing.owned(s,fid,uid,sid,lock=True,allow_deleted=True)
    if row.state in ('deleting','deleting_run','deleted'):return row
    if row.state=='delete_failed':row.state='deleting';s.commit();return row
    interviewing.cancel_questions(s,row)
    s.query(InterviewAsrTask).filter_by(session_id=sid).update({InterviewAsrTask.status:'cancelled',InterviewAsrTask.usage:None},synchronize_session=False)
    clips=s.query(InterviewClip).filter_by(session_id=sid).all()
    source_ids={row.record_id} if row.record_id else set()
    for clip in clips:
        source_ids.add(hashlib.sha256((fid+'\0'+uid+'\0asr-source-'+clip.id).encode()).hexdigest())
        clip.status='deleting';clip.transcript=None;clip.usage=None
    from organizing import delete
    for rid in source_ids:
        if s.query(OrganizeRecord).filter_by(id=rid,family_id=fid,user_id=uid,del_flag=0).first():delete(s,fid,uid,rid,acknowledge_story=True,commit=False)
    s.query(InterviewAnswer).filter_by(session_id=sid).delete(synchronize_session=False)
    row.state='deleting';row.ai_consent=False;row.narrator_id=None;row.subject_id=None;row.narrator_label=None;row.record_id=None
    row.question='原材料删除中';row.topic='free';row.recording_mode='unspecified';row.revision+=1;row.update_date=local_now()
    s.commit();return row


def retry(s,fid,uid,sid):
    row=interviewing.owned(s,fid,uid,sid,lock=True,allow_deleted=True)
    if row.state=='delete_failed':row.state='deleting';s.commit()
    return row


def purge_one():
    s=get_session();now=local_now();expired=now-datetime.timedelta(minutes=5)
    row=s.query(InterviewSession).filter(or_(InterviewSession.state=='deleting',and_(InterviewSession.state.in_(('deleting_run','delete_failed')),InterviewSession.update_date<expired))).order_by(InterviewSession.update_date).with_for_update().first()
    if not row:return False
    sid=row.id;previous=row.state;previous_time=row.update_date;token=uuid4().hex
    if s.query(InterviewSession).filter_by(id=sid,state=previous,update_date=previous_time).update({InterviewSession.state:'deleting_run',InterviewSession.update_date:now,InterviewSession.remarks:token},synchronize_session=False)!=1:
        s.rollback();return False
    keys=[c.storage_key for c in s.query(InterviewClip).filter_by(session_id=sid).all()];s.commit()
    try:
        for key in keys:interview_audio.delete(key)
        s.rollback();row=s.query(InterviewSession).filter_by(id=sid,state='deleting_run',remarks=token).with_for_update().first()
        if not row:return True
        for model in (InterviewAnswer,InterviewQuestion,InterviewAsrTask,InterviewClip):
            model_session=model.session_id
            s.query(model).filter(model_session==sid).delete(synchronize_session=False)
        row.state='deleted';row.question='原材料已删除';row.update_date=local_now();s.commit()
    except Exception:
        s.rollback();s.query(InterviewSession).filter_by(id=sid,state='deleting_run',remarks=token).update({InterviewSession.state:'delete_failed',InterviewSession.update_date:local_now()},synchronize_session=False);s.commit()
    return True
