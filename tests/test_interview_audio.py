import io
import math
import wave
import shutil
from array import array

import pytest
from werkzeug.exceptions import HTTPException

import interviewing
import interview_audio
from models import FamilyMember, InterviewClip, get_session
from storage import storage_url


def wav(silent=False, seconds=.2):
    output=io.BytesIO()
    with wave.open(output,'wb') as audio:
        audio.setparams((1,2,16000,0,'NONE','not compressed'))
        audio.writeframes(array('h',[0 if silent else int(3000*math.sin(i/16000*440*2*math.pi)) for i in range(int(seconds*16000))]).tobytes())
    return output.getvalue()


def setup(app):
    path=shutil.which('ffmpeg')
    if not path: pytest.skip('ffmpeg is required for media validation')
    app.config.update(VOICE_FFMPEG=path,STORAGE_BACKEND='local')
    return interviewing.start(get_session(),'a','member-a',{},'interview-test').id


def test_private_short_audio_and_idempotent_upload(app,client,login):
    sid=setup(app)
    with app.app_context():
        s=get_session();clip=interview_audio.upload(s,'a','member-a',sid,1,'upload-test',wav(),True)
        cid,key=clip.id,clip.storage_key
        from legal import PRIVACY_VERSION
        assert clip.remarks=='recording-storage-v1;policy='+PRIVACY_VERSION
        assert interview_audio.upload(s,'a','member-a',sid,1,'upload-test',wav(),True).id==cid
        assert s.query(InterviewClip).count()==1 and clip.duration_ms==200
        assert storage_url(key)==''
        with pytest.raises(HTTPException): interview_audio.upload(s,'a','member-a',sid,1,'upload-test',wav(seconds=.3),True)
    path='/f/a/interview/'+sid+'/audio/'+cid
    login('member-a'); response=client.get(path)
    assert response.status_code==200 and response.data[:4]==b'RIFF' and 'no-store' in response.headers['Cache-Control']
    assert client.get('/uploads/'+key).status_code==404
    login('owner-a'); assert client.get(path).status_code==404
    login('member-a');get_session().get(FamilyMember,'member').del_flag=1;get_session().commit()
    assert client.get(path).status_code==404


def test_consent_silence_corrupt_and_account_key_isolation(app):
    sid=setup(app)
    with app.app_context():
        assert interview_audio.local_identity('member-a')['key']!=interview_audio.local_identity('owner-a')['key']
        for data,consent in [(wav(),False),(wav(silent=True),True),(b'not audio',True)]:
            with pytest.raises(HTTPException): interview_audio.upload(get_session(),'a','member-a',sid,1,'upload-test',data,consent)
            get_session().rollback()
        assert get_session().query(InterviewClip).count()==0


def test_duplicate_upload_finishing_after_answer_advanced_reuses_clip(app,monkeypatch):
    sid=setup(app);s=get_session()
    with app.app_context():
        original=interview_audio.normalize; entered=[]
        def interleaved(data):
            result=original(data)
            if not entered:
                entered.append(True)
                clip=interview_audio.upload(s,'a','member-a',sid,1,'upload-race',data,True)
                interviewing.answer(s,'a','member-a',sid,1,'answer-race','一句已保存的回答。',clip_id=clip.id)
            return result
        monkeypatch.setattr(interview_audio,'normalize',interleaved)
        clip=interview_audio.upload(s,'a','member-a',sid,1,'upload-race',wav(),True)
        assert clip.answer_id and s.query(InterviewClip).count()==1
