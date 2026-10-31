"""Interview recordings stay private; they never become voice-clone samples."""
import base64
import hashlib
import hmac
import datetime
from uuid import uuid4
from sqlalchemy.exc import IntegrityError
from reporting import local_now
import io
import os
from pathlib import Path
import re
import subprocess
import tempfile
import wave
from array import array

from flask import abort, current_app
from models import InterviewClip
import interviewing
from voice_storage import backend


def local_identity(uid):
    secret = current_app.secret_key
    if isinstance(secret,str): secret=secret.encode()
    key = hmac.new(secret, ('interview-device-v1\0'+uid).encode(), hashlib.sha256).digest()
    return {'owner': hashlib.sha256(uid.encode()).hexdigest(), 'key': base64.b64encode(key).decode()}


def check(key):
    if not isinstance(key,str) or not re.fullmatch(r'interview/[A-Za-z0-9_-]{1,64}/[a-f0-9]{64}\.wav',key): abort(404)


def read(key):
    check(key)
    data=backend().read(key, 6*1024*1024+1)
    if len(data)>6*1024*1024: abort(503,'录音暂时无法读取，请稍后重试。')
    return data


def delete(key):
    check(key);store=backend()
    if hasattr(store,'upload_dir'):store.delete(key)
    else:
        result=store.client.delete_object(store._oss.DeleteObjectRequest(bucket=store.bucket,key=key))
        if result.status_code not in (200,204,404):raise RuntimeError('private audio deletion failed')


def save(data,key):
    check(key); store=backend()
    if not hasattr(store,'upload_dir'): store.save(data,key); return
    root=Path(store.upload_dir).resolve(); target=root/key
    parent=root
    for part in Path(key).parts[:-1]:
        parent=parent/part
        if parent.is_symlink(): raise ValueError('private storage path')
        parent.mkdir(mode=0o700,parents=True,exist_ok=True); parent.chmod(0o700)
    if root not in target.resolve().parents: raise ValueError('private storage path')
    temp=None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent,prefix='.private-',delete=False) as out:
            temp=Path(out.name); out.write(data); out.flush(); os.fsync(out.fileno())
        os.replace(temp,target)
    finally:
        if temp: temp.unlink(missing_ok=True)


def normalize(data):
    with tempfile.TemporaryDirectory(prefix='memoir-interview-') as directory:
        source=Path(directory)/'input'; target=Path(directory)/'audio.wav'; source.write_bytes(data); source.chmod(0o600)
        try:
            subprocess.run([current_app.config['VOICE_FFMPEG'],'-v','error','-protocol_whitelist','file,pipe',
                '-format_whitelist','wav,mp3,mov,matroska,webm,ogg,aac','-i',str(source),'-t','181',
                '-vn','-ac','1','-ar','16000','-c:a','pcm_s16le',str(target)],capture_output=True,timeout=30,check=True)
            with wave.open(str(target)) as audio:
                duration=audio.getnframes()/16000
                if not .05<=duration<=180.1: abort(400,'单段录音最长3分钟；超时文件请先分段，本站不会静默截断。')
                frames=audio.readframes(audio.getnframes())
            samples=array('h'); samples.frombytes(frames)
            if not samples or max(abs(v) for v in samples)<32: abort(400,'没有检测到声音，请检查麦克风并回听。')
            return target.read_bytes(), round(duration*1000)
        except (OSError,ValueError,EOFError,wave.Error,subprocess.SubprocessError):
            abort(400,'无法处理该录音，请改用手机录音文件或文字回答。')


def upload(s,fid,uid,sid,revision,nonce,data,consent):
    row=interviewing.owned(s,fid,uid,sid)
    if not consent: abort(400,'请先确认本人同意，或已向实际讲述者说明并取得同意；本次录音不包含声音复刻授权。')
    cid=interviewing.nonce_id('clip',sid,uid,nonce); digest=hashlib.sha256(data).hexdigest()
    def prior(lock=False):
        query=s.query(InterviewClip).filter_by(id=cid,session_id=sid,user_id=uid,del_flag=0)
        clip=(query.with_for_update() if lock else query).populate_existing().first()
        if clip and clip.source_hash!=digest: abort(409,'此上传编号已用于另一段录音，请重新选择。')
        return clip
    old=prior()
    if old and (old.status not in ('uploading','upload_failed') or (old.status=='uploading' and old.lease_until and old.lease_until>local_now())): return old
    if not data or len(data)>current_app.config['INTERVIEW_MAX_UPLOAD_BYTES']: abort(413,'录音文件过大，请分段上传。')
    s.commit()  # Do not keep a database read transaction while decoding media.
    audio,duration=normalize(data)
    row=interviewing.owned(s,fid,uid,sid,lock=True)
    old=prior(True)
    if old and (old.status not in ('uploading','upload_failed') or (old.status=='uploading' and old.lease_until and old.lease_until>local_now())): return old
    if not old:
        if str(row.revision)!=str(revision):abort(409,'采访进度已变化，片段仍保留在本机，可先下载。')
        if row.state!='active' or interviewing.pending(s,row):abort(409,'采访进度已变化，录音保留在本机；请先恢复对应问题。')
        if s.query(InterviewClip).filter_by(session_id=sid,del_flag=0).count()>=100:abort(400,'本段录音已达到100个片段，请先整理本段。')
    key='interview/'+fid+'/'+cid+'.wav';token=uuid4().hex
    from legal import PRIVACY_VERSION
    clip=old or InterviewClip(id=cid,family_id=fid,user_id=uid,session_id=sid,input_revision=row.revision,
        question=row.question,source_hash=digest,storage_key=key,duration_ms=duration,create_by=uid,remarks='recording-storage-v1;policy='+PRIVACY_VERSION)
    clip.status='uploading';clip.lease_token=token;clip.lease_until=local_now()+datetime.timedelta(seconds=60)
    s.add(clip)
    try:s.commit()
    except IntegrityError:
        s.rollback();clip=prior()
        if clip:return clip
        raise
    # Only the reservation owner writes storage. A duplicate must never delete the winner's file.
    try:save(audio,key)
    except Exception:
        s.query(InterviewClip).filter_by(id=cid,status='uploading',lease_token=token).update({InterviewClip.status:'upload_failed'},synchronize_session=False)
        s.commit();abort(503,'服务器尚未保存录音，本机片段请保留后重试。')
    s.expire_all();clip=s.get(InterviewClip,cid)
    if not clip or clip.status in ('deleting','deleted') or clip.del_flag:
        delete(key);abort(404)
    s.query(InterviewClip).filter_by(id=cid,status='uploading',lease_token=token).update({InterviewClip.status:'uploaded',InterviewClip.lease_until:None},synchronize_session=False)
    s.commit();s.refresh(clip);return clip


def owned_clip(s,fid,uid,sid,cid):
    interviewing.owned(s,fid,uid,sid)
    clip=s.query(InterviewClip).filter_by(id=cid,session_id=sid,family_id=fid,user_id=uid,del_flag=0).first()
    if not clip or clip.status in ('deleting','deleted','uploading','upload_failed'): abort(404)
    return clip
