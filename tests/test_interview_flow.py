import pytest
from werkzeug.exceptions import HTTPException

import interviewing as iv
import interview_questions as questions
import organizing
from models import InterviewAnswer, InterviewQuestion, OrganizeRecord, OrganizeSource, get_session


@pytest.fixture(autouse=True)
def context(app):
    with app.app_context(): yield


def start():
    return iv.start(get_session(),'a','member-a',{'ai_consent':'yes'},'interview-start').id


def test_two_followups_then_next_topic_and_no_duplicate_answers(app):
    s=get_session(); sid=start()
    for i in range(3):
        row=iv.owned(s,'a','member-a',sid)
        version=row.revision; old_question=row.question
        iv.answer(s,'a','member-a',sid,version,'answer-'+str(i),'小时候在河边玩。')
        iv.answer(s,'a','member-a',sid,version,'answer-'+str(i),'小时候在河边玩。')
        assert len(iv.answers(s,sid)) == i+1
        assert iv.answers(s,sid)[i].question == old_question
    assert row.topic=='family' and row.followups==0
    iv.finish(s,'a','member-a',sid,row.revision)
    rid=row.record_id
    assert s.get(OrganizeRecord,rid).content.count('答：小时候')==3
    assert iv.finish(s,'a','member-a',sid,1).record_id==rid
    first=iv.answers(s,sid)[0]
    iv.edit_answer(s,'a','member-a',sid,row.revision,first.id,1,'实际是在山脚玩。')
    assert s.get(OrganizeRecord,rid).revision==2 and first.history[0]['content']=='小时候在河边玩。'
    assert s.query(OrganizeSource).filter_by(record_id=rid).count()==2
    assert '山脚' in s.get(OrganizeRecord,rid).content


def test_queued_followup_is_private_bounded_and_late_result_is_discarded(app):
    s=get_session(); sid=start()
    app.config.update(ORGANIZE_ENABLED=True,INTERVIEW_AI_ENABLED=True,INAPP_AI_DATA_APPROVED=True,DEEPSEEK_API_KEY='test-only')
    with app.app_context():
        iv.answer(s,'a','member-a',sid,1,'answer-11','我和妈妈去河边。')
        assert iv.pending(s,iv.owned(s,'a','member-a',sid))
        calls=[]
        def provider(payload):
            calls.append(payload)
            return '在河边时最记得什么？',{'total_tokens':5}
        assert questions.run_one(provider)
        row=iv.owned(s,'a','member-a',sid)
        assert row.question=='在河边时最记得什么？'
        assert calls[0]['answers'][0]['answer']=='我和妈妈去河边。'
        iv.answer(s,'a','member-a',sid,row.revision,'answer-22','妈妈帮我捞起鞋子。')
        def late(payload):
            row=iv.owned(s,'a','member-a',sid)
            iv.pause(s,'a','member-a',sid,row.revision)
            return '不应覆盖的问题？',{}
        questions.run_one(late)
        assert iv.owned(s,'a','member-a',sid).state=='paused'
        assert '不应' not in iv.owned(s,'a','member-a',sid).question
        assert s.query(InterviewQuestion).filter_by(status='cancelled').count()==1


def test_old_forms_and_oversized_answers_cannot_overwrite(app):
    s=get_session(); sid=start()
    with pytest.raises(HTTPException): iv.answer(s,'a','member-a',sid,1,'answer-11','超'*4001)
    iv.answer(s,'a','member-a',sid,1,'answer-11','一句也可以。')
    with pytest.raises(HTTPException): iv.answer(s,'a','member-a',sid,1,'answer-22','旧页面')
    assert len(iv.answers(s,sid))==1
    with pytest.raises(HTTPException): iv.edit_answer(s,'a','owner-a',sid,2,iv.answers(s,sid)[0].id,1,'管理员不应读取')
