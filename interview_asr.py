"""Aliyun ASR with private byte input, explicit consent, durable attempts and no blind replay."""
import base64
import datetime
import json
import math
import re
from uuid import uuid4
from urllib.parse import urlparse

import requests
from flask import abort, current_app

import interviewing
import interview_audio
from models import InterviewAsrTask, InterviewClip, User, get_session
from organize_provider import GenerationError
from reporting import local_now


def enabled():
    c=current_app.config
    url=urlparse(c.get('INTERVIEW_ASR_BASE_URL',''))
    safe=url.scheme=='https' and bool(re.fullmatch(r'(?:[a-zA-Z0-9-]+\.)*aliyuncs\.com',url.hostname or '')) and not url.username and not url.password and not url.query and not url.fragment and (url.netloc==url.hostname or url.netloc==url.hostname+':443')
    return bool(c.get('INTERVIEW_ASR_ENABLED') and c.get('INTERVIEW_ASR_DATA_APPROVED') and c.get('INTERVIEW_ASR_API_KEY') and safe)


def begin(s,fid,uid,sid,cid,nonce,consent=False,retry=False):
    row=interviewing.owned(s,fid,uid,sid,lock=True)
    clip=interview_audio.owned_clip(s,fid,uid,sid,cid)
    tid=interviewing.nonce_id('asr',cid,uid,nonce)
    old=s.query(InterviewAsrTask).filter_by(id=tid).with_for_update().populate_existing().first()
    if old: return old
    active=s.query(InterviewAsrTask).filter_by(clip_id=cid).filter(InterviewAsrTask.status.in_(('queued','running','succeeded'))).with_for_update().first()
    if active: return active
    if clip.transcript is not None: abort(409,'本段已有原始转写，请直接核对文字，不重复产生转写费用。')
    if not consent or not enabled(): abort(400,'请先确认将本段录音交给阿里云转写；未开通时仍可回听或填写文字。')
    prior=s.query(InterviewAsrTask.id).filter_by(clip_id=cid).with_for_update().first()
    if prior and not retry: abort(409,'上次转写未完成或结果未知，重新发起可能再次计费，请明确确认后重试。')
    s.query(User).filter_by(id=uid,del_flag=0).with_for_update().one()
    start=local_now().replace(hour=0,minute=0,second=0,microsecond=0)
    rows=s.query(InterviewAsrTask.duration_ms).filter(InterviewAsrTask.user_id==uid,InterviewAsrTask.create_date>=start).with_for_update().all()
    if len(rows)>=current_app.config['INTERVIEW_ASR_DAILY_TASKS'] or sum(r[0] for r in rows)+clip.duration_ms>current_app.config['INTERVIEW_ASR_DAILY_SECONDS']*1000:
        abort(429,'今日转写额度已用完，录音已保存，仍可回听或人工填写。')
    from legal import PRIVACY_VERSION
    task=InterviewAsrTask(id=tid,family_id=fid,user_id=uid,session_id=sid,clip_id=cid,status='queued',
        model=current_app.config['INTERVIEW_ASR_MODEL'],duration_ms=clip.duration_ms,create_by=uid,create_date=local_now(),remarks='recording-asr-consent-v1;policy='+PRIVACY_VERSION)
    clip.consent_asr=True;s.add(task);s.commit();return task


def generate(audio,model):
    c=current_app.config
    # No public or signed URL. Regional/workspace endpoint must be configured explicitly.
    body={'model':model,'messages':[{'role':'user','content':[{'type':'input_audio','input_audio':{'data':'data:audio/wav;base64,'+base64.b64encode(audio).decode()}}]}],
        'stream':False,'asr_options':{'enable_itn':False}}
    try:
        r=requests.post(c['INTERVIEW_ASR_BASE_URL'].rstrip('/')+'/chat/completions',headers={'Authorization':'Bearer '+c['INTERVIEW_ASR_API_KEY']},json=body,timeout=(10,120),stream=True)
    except requests.RequestException: raise GenerationError('connection_unknown',True) from None
    try:
        if r.status_code!=200: raise GenerationError('provider_unavailable',r.status_code>=500)
        raw=bytearray()
        for chunk in r.iter_content(16384):
            raw.extend(chunk)
            if len(raw)>256*1024: raise GenerationError()
        blob=json.loads(raw);choice=blob['choices'][0]
        if choice.get('finish_reason')!='stop': raise GenerationError()
        text=choice['message']['content']
        if not isinstance(text,str) or len(text)>20000: raise GenerationError()
        usage={k:v for k,v in (blob.get('usage') or {}).items() if k in ('total_tokens','input_tokens','output_tokens','seconds') and type(v) in (int,float) and math.isfinite(v) and v>=0}
        return text.strip(),usage
    except requests.RequestException: raise GenerationError('connection_unknown',True) from None
    except (KeyError,ValueError,TypeError,IndexError): raise GenerationError() from None
    finally:r.close()


def run_one(provider=None):
    s=get_session();now=local_now()
    s.query(InterviewAsrTask).filter(InterviewAsrTask.status=='running',InterviewAsrTask.lease_until<now).update({InterviewAsrTask.status:'uncertain'},synchronize_session=False);s.commit()
    if not enabled():return False
    task=s.query(InterviewAsrTask).filter_by(status='queued').order_by(InterviewAsrTask.create_date).with_for_update().first()
    if not task:return False
    tid=task.id;token=uuid4().hex
    if not s.query(InterviewAsrTask).filter_by(id=tid,status='queued').update({InterviewAsrTask.status:'running',InterviewAsrTask.lease_token:token,
        InterviewAsrTask.lease_until:now+datetime.timedelta(minutes=3)},synchronize_session=False):s.rollback();return False
    s.commit()
    try:
        task=s.get(InterviewAsrTask,tid)
        clip=interview_audio.owned_clip(s,task.family_id,task.user_id,task.session_id,task.clip_id)
        if not clip.consent_asr:raise Stale()
        audio=interview_audio.read(clip.storage_key);model=task.model;s.commit()
        current=s.query(InterviewAsrTask).filter_by(id=tid,status='running',lease_token=token).first()
        if not current:raise Stale()
        allowed=interview_audio.owned_clip(s,task.family_id,task.user_id,task.session_id,task.clip_id)
        if not allowed.consent_asr:raise Stale()
        s.commit()
        text,usage=(provider or generate)(audio,model)
        if not isinstance(text,str) or len(text)>20000:raise GenerationError()
        s.rollback();s.expire_all();task=s.get(InterviewAsrTask,tid)
        row=interviewing.owned(s,task.family_id,task.user_id,task.session_id,lock=True)
        clip=interview_audio.owned_clip(s,task.family_id,task.user_id,task.session_id,task.clip_id)
        task=s.query(InterviewAsrTask).filter_by(id=tid).with_for_update().populate_existing().one()
        if task.status!='running' or task.lease_token!=token:s.rollback();return True
        if not clip.consent_asr:raise Stale()
        clip.transcript,clip.usage,clip.model=text,usage,model
        task.usage,task.status=usage,'succeeded'
        clip.status='review'
        if text.strip() and len(text)<=4000 and row.state=='active' and row.revision==clip.input_revision and not clip.answer_id and not interviewing.pending(s,row):
            # Commit ASR, answer and follow-up together. No automatic publication.
            interviewing.answer(s,row.family_id,row.user_id,row.id,row.revision,'clip-'+clip.id,text,clip_id=clip.id)
        else:s.commit()
    except Exception as exc:
        s.rollback()
        state='outdated' if isinstance(exc,Stale) or getattr(exc,'code',None)==404 else ('uncertain' if getattr(exc,'uncertain',False) else 'failed')
        # If transcription finished but answer acceptance failed, preserve that result for human recovery.
        task=s.query(InterviewAsrTask).filter_by(id=tid,status='running',lease_token=token).first()
        if task:
            if state!='outdated' and 'text' in locals() and isinstance(text,str) and len(text)<=20000:
                try:
                    clip=interview_audio.owned_clip(s,task.family_id,task.user_id,task.session_id,task.clip_id)
                    clip.transcript,clip.status,clip.usage=text,'review',usage
                    task.status,task.usage='succeeded',usage
                except Exception:s.rollback();return True
            else:task.status=state
            s.commit()
    return True


class Stale(Exception):pass
