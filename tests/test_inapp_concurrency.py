"""Independent SQLite sessions: duplicate clicks cannot duplicate billable tasks or drafts."""
import threading

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

import models
import organizing
import organize_preview
import organize_jobs
import organize_drafts
import interviewing
import interview_audio
import interview_asr
from test_interview_audio import wav


@pytest.mark.parametrize('operation',['generate','confirm','answer','upload','asr'])
def test_two_independent_connections_one_logical_operation(app,tmp_path,monkeypatch,operation):
    engine=create_engine('sqlite:///'+str(tmp_path/'concurrent.db'))
    models.Base.metadata.create_all(engine)
    sessions=scoped_session(sessionmaker(bind=engine));monkeypatch.setattr(models,'_Session',sessions)
    s=sessions();s.add_all([models.User(id='u'),models.Family(id='f',owner_user_id='u'),models.FamilyMember(id='m',family_id='f',user_id='u',role='owner')]);s.commit()
    rid=organizing.create(s,'f','u',{'content':'一段测试回忆'}).id
    organize_preview.manual(s,'f','u',rid,1,0)
    sid=interviewing.start(s,'f','u',{},'session-start').id
    monkeypatch.setattr(interview_audio,'normalize',lambda data:(wav(),200))
    app.config.update(STORAGE_BACKEND='local',ORGANIZE_ENABLED=True,INAPP_AI_DATA_APPROVED=True,DEEPSEEK_API_KEY='synthetic-only',
        INTERVIEW_ASR_ENABLED=True,INTERVIEW_ASR_DATA_APPROVED=True,INTERVIEW_ASR_API_KEY='synthetic-only',INTERVIEW_ASR_BASE_URL='https://test.cn-beijing.maas.aliyuncs.com/compatible-mode/v1')
    with app.app_context():cid=interview_audio.upload(s,'f','u',sid,1,'initial-audio',wav(),True).id
    sessions.remove();barrier=threading.Barrier(2);results=[];errors=[]
    def submit(index):
        try:
            with app.app_context():
                barrier.wait(timeout=10);s=sessions()
                if operation=='generate':value=organize_jobs.begin('f','u',rid,1,'request-'+str(index),True).id
                elif operation=='confirm':value=organize_drafts.confirm(s,'f','u',rid,1,1,'confirm-'+str(index)).id
                elif operation=='answer':value=interviewing.answer(s,'f','u',sid,1,'same-answer','一句回答。').id
                elif operation=='upload':value=interview_audio.upload(s,'f','u',sid,1,'same-audio',wav(),True).id
                else:value=interview_asr.begin(s,'f','u',sid,cid,'asr-start-'+str(index),True).id
                results.append(value)
        except Exception as exc:errors.append(type(exc).__name__)
        finally:sessions.remove()
    threads=[threading.Thread(target=submit,args=(i,)) for i in range(2)]
    try:
        for thread in threads:thread.start()
        for thread in threads:thread.join(timeout=15)
        assert not any(t.is_alive() for t in threads) and not errors
        assert len(results)==2 and len(set(results))==1
        s=sessions()
        if operation=='generate':assert s.query(models.OrganizeTask).count()==1
        elif operation=='confirm':assert s.query(models.Interview).count()==1 and s.query(models.Draft).count()==1
        elif operation=='answer':assert s.query(models.InterviewAnswer).count()==1
        elif operation=='upload':
            assert s.query(models.InterviewClip).count()==2
            clip=s.get(models.InterviewClip,results[0]);assert clip.status=='uploaded'
            with app.app_context():assert interview_audio.read(clip.storage_key)[:4]==b'RIFF'
        else:assert s.query(models.InterviewAsrTask).count()==1
    finally:
        for thread in threads:thread.join(timeout=15)
        sessions.remove();engine.dispose()
