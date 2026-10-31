import json

import pytest
import requests
from werkzeug.exceptions import HTTPException

import interview_asr as asr
import interview_audio as audio
import interviewing as iv
from models import FamilyMember, InterviewAsrTask, InterviewClip, InterviewAnswer, get_session
from test_interview_audio import wav, setup


@pytest.fixture
def prepared(app):
    sid=setup(app)
    app.config.update(INTERVIEW_ASR_ENABLED=True,INTERVIEW_ASR_DATA_APPROVED=True,INTERVIEW_ASR_API_KEY='synthetic-only',
        INTERVIEW_ASR_BASE_URL='https://test.cn-beijing.maas.aliyuncs.com/compatible-mode/v1')
    with app.app_context():
        clip=audio.upload(get_session(),'a','member-a',sid,1,'upload-asr',wav(),True)
        yield sid,clip.id


def test_transcription_accepts_answer_once_and_keeps_original_for_correction(app,prepared):
    sid,cid=prepared;s=get_session()
    task=asr.begin(s,'a','member-a',sid,cid,'asr-start-1',True);tid=task.id
    assert asr.begin(s,'a','member-a',sid,cid,'asr-start-2',True).id==tid
    calls=[]
    assert asr.run_one(lambda data,model:(calls.append(len(data)) or '我小时候住在河边。',{'seconds':.2}))
    clip=s.get(InterviewClip,cid);answer=s.query(InterviewAnswer).one();row=iv.owned(s,'a','member-a',sid)
    assert clip.answer_id==answer.id and clip.transcript=='我小时候住在河边。'
    iv.edit_answer(s,'a','member-a',sid,row.revision,answer.id,answer.version,'我小时候住在山边。')
    assert clip.transcript=='我小时候住在河边。' and answer.history[0]['content']==clip.transcript
    assert not asr.run_one(lambda *args:pytest.fail('must not call again'))
    assert len(calls)==1


@pytest.mark.parametrize('action',['pause','remove'])
def test_stale_or_removed_member_cannot_auto_accept(app,prepared,action):
    sid,cid=prepared;s=get_session();tid=asr.begin(s,'a','member-a',sid,cid,'asr-start-1',True).id
    def late(*args):
        if action=='pause':iv.pause(s,'a','member-a',sid,1)
        else:s.get(FamilyMember,'member').del_flag=1;s.commit()
        return '迟到的转写',{}
    asr.run_one(late)
    assert s.query(InterviewAnswer).count()==0
    clip=s.get(InterviewClip,cid)
    if action=='pause': assert clip.transcript=='迟到的转写' and clip.status=='review'
    else: assert clip.transcript is None and s.get(InterviewAsrTask,tid).status=='outdated'


def test_timeout_requires_explicit_new_attempt_and_quota_keeps_audio(app,prepared):
    from organize_provider import GenerationError
    sid,cid=prepared;s=get_session();tid=asr.begin(s,'a','member-a',sid,cid,'asr-start-1',True).id
    asr.run_one(lambda *args:(_ for _ in ()).throw(GenerationError('connection_unknown',True)))
    assert s.get(InterviewAsrTask,tid).status=='uncertain'
    with pytest.raises(HTTPException):asr.begin(s,'a','member-a',sid,cid,'asr-start-2',True)
    s.rollback();app.config['INTERVIEW_ASR_DAILY_TASKS']=1
    with pytest.raises(HTTPException) as err:asr.begin(s,'a','member-a',sid,cid,'asr-start-2',True,True)
    assert err.value.code==429 and audio.read(s.get(InterviewClip,cid).storage_key)[:4]==b'RIFF'


def test_aliyun_private_base64_contract_without_outbound_call(app,prepared,monkeypatch):
    calls=[]
    class Response:
        status_code=200
        def iter_content(self,size):yield json.dumps({'choices':[{'finish_reason':'stop','message':{'content':'一句回忆'}}],
            'usage':{'total_tokens':5,'private':'excluded'}}).encode()
        def close(self):pass
    def post(url,**kwargs):calls.append((url,kwargs));return Response()
    monkeypatch.setattr(requests,'post',post)
    assert asr.generate(wav(),'qwen3-asr-flash')==('一句回忆',{'total_tokens':5})
    assert calls[0][1]['json']['messages'][0]['content'][0]['input_audio']['data'].startswith('data:audio/wav;base64,')
    assert 'https://' not in str(calls[0][1]['json'])
