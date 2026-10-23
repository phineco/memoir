"""Private audio: application-authorized bytes only, no public/signed browser URLs."""
import io
from array import array
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import os
import shutil
import wave

from flask import current_app

from voice_provider import VoiceError


def backend():
    from storage import LocalStorageBackend,OssStorageBackend
    config=current_app.config
    if config['STORAGE_BACKEND']=='local':return LocalStorageBackend(config['UPLOAD_DIR'])
    return OssStorageBackend(config['OSS_REGION'],config['OSS_BUCKET'],config['OSS_ACCESS_KEY_ID'],
                             config['OSS_ACCESS_KEY_SECRET'],config['OSS_ENDPOINT'],config['OSS_URL_EXPIRES'])


def check_key(key):
    if not isinstance(key,str) or not re.fullmatch(r'voice/[A-Za-z0-9_-]{1,64}/[a-f0-9]{32}/[1-9][0-9]*/(?:sample|[a-f0-9]{64})\.wav',key):raise VoiceError('storage')


def read(key,limit=100*1024*1024):
    check_key(key)
    store=backend()
    if hasattr(store,'upload_dir'):
        root=Path(store.upload_dir).resolve();path=(root/key).resolve()
        if root not in path.parents or path.is_symlink() or path.stat().st_size>limit:raise VoiceError('storage')
        return path.read_bytes()
    result=store.client.get_object(store._oss.GetObjectRequest(bucket=store.bucket,key=key))
    try:
        data=result.body.read(limit+1)
        if len(data)>limit:raise VoiceError('storage')
        return data
    finally:
        if hasattr(result.body,'close'):result.body.close()


def save(data,key):
    check_key(key)
    store=backend()
    if not hasattr(store,'upload_dir'):
        store.save(data,key);return
    root=Path(store.upload_dir).resolve();target=root/key
    if root not in target.resolve().parents:raise VoiceError('storage')
    parent=root
    for part in Path(key).parts[:-1]:
        parent=parent/part;parent.mkdir(mode=0o700,parents=True,exist_ok=True);parent.chmod(0o700)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent,prefix='.private-',delete=False) as handle:
            temporary=Path(handle.name);handle.write(data);handle.flush();os.fsync(handle.fileno())
        os.replace(temporary,target)
    finally:
        if temporary:temporary.unlink(missing_ok=True)


def delete(key):
    if not key:return
    check_key(key)
    store=backend()
    if hasattr(store,'upload_dir'):
        root=Path(store.upload_dir).resolve()
        if root not in (root/key).resolve().parents:raise VoiceError('storage')
        store.delete(key)
    else:
        result=store.client.delete_object(store._oss.DeleteObjectRequest(bucket=store.bucket,key=key))
        if result.status_code not in (200,204):raise VoiceError('storage_delete')


def purge_local_profile(family_id,profile_id):
    check_key(f'voice/{family_id}/{profile_id}/1/sample.wav')
    store=backend()
    if not hasattr(store,'upload_dir'):return
    root=Path(store.upload_dir).resolve();folder=root/'voice'/family_id/profile_id
    if root not in folder.resolve().parents or folder.is_symlink():raise VoiceError('storage_delete')
    if folder.exists():shutil.rmtree(folder)


def normalize_sample(data,start,length):
    if not data or len(data)>10*1024*1024 or not 0<=start<=300 or not 10<=length<=60:raise VoiceError('sample_invalid')
    with tempfile.TemporaryDirectory(prefix='memoir-voice-') as directory:
        source=Path(directory)/'source';output=Path(directory)/'decoded.wav';source.write_bytes(data);source.chmod(0o600)
        common=['-v','error','-protocol_whitelist','file,pipe','-format_whitelist','wav,mp3,mov,matroska,webm,ogg,aac']
        try:
            # MediaRecorder WebM often has no duration header. Decode with a hard frame/time cap.
            subprocess.run([current_app.config['VOICE_FFMPEG'],*common,'-i',str(source),'-t','301','-vn','-ac','1','-ar','24000','-c:a','pcm_s16le',str(output)],capture_output=True,timeout=30,check=True)
            with wave.open(str(output)) as sound:
                duration=sound.getnframes()/sound.getframerate()
                if not 10<=duration<=300 or start+length>duration+.05:raise VoiceError('sample_invalid')
                sound.setpos(int(start*24000));frames=sound.readframes(int(length*24000))
            samples=array('h');samples.frombytes(frames)
            if not samples or max(abs(value) for value in samples)<32:raise VoiceError('sample_silent')
            result=io.BytesIO()
            with wave.open(result,'wb') as clip:
                clip.setparams((1,2,24000,0,'NONE','not compressed'));clip.writeframes(frames)
            return result.getvalue()
        except VoiceError:raise
        except (OSError,ValueError,KeyError,subprocess.SubprocessError,wave.Error):raise VoiceError('sample_processing') from None


def label_audio(data,identifier):
    try:
        with wave.open(io.BytesIO(data)) as audio:
            if audio.getnframes()==0 or audio.getcomptype()!='NONE':raise VoiceError('audio_invalid',True)
    except (wave.Error,EOFError):raise VoiceError('audio_invalid',True) from None
    # Append metadata; preserve original provider chunks/markers byte-for-byte.
    payload=('家音 / AI 合成声音 / '+identifier).encode('utf-8')+b'\0'
    info=b'INFO'+b'ICMT'+struct.pack('<I',len(payload))+payload+(b'\0' if len(payload)%2 else b'')
    chunk=b'LIST'+struct.pack('<I',len(info))+info
    output=data+chunk
    return output[:4]+struct.pack('<I',len(output)-8)+output[8:]
