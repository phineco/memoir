import re

import pytest
from sqlalchemy import event

import ai
import ai_memory
import ai_turns
import models
from models import AiMemory,AiMessage,FamilyMember,Interview,Draft,get_session


def csrf(client):
    body=client.get('/account/ai-memory?family_id=a').get_data(as_text=True)
    return re.search(r'name="csrf_token" value="([^"]+)"',body).group(1)


def seed_memory():
    s=get_session();stamp=ai.user_context_stamp('a','owner-a')
    s.add_all([AiMemory(id='own',family_id='a',user_id='owner-a',memory_key=stamp,content='OWN_OLD_SUMMARY'),
               AiMemory(id='other-version',family_id='a',user_id='owner-a',memory_key='older-version',content='OLDER_SUMMARY'),
               AiMemory(id='other-user',family_id='a',user_id='member-a',memory_key=stamp,content='OTHER_USER_SUMMARY'),
               AiMessage(id='old-message',family_id='a',user_id='owner-a',role='user',content='OLD_PREFERENCE',remarks=stamp)])
    s.commit();return stamp


def test_reset_excludes_all_old_summaries_and_history_from_new_requests(client,login,monkeypatch):
    login();stamp=seed_memory();token=csrf(client)
    body=client.get('/account/ai-memory?family_id=a').get_data(as_text=True)
    assert 'OWN_OLD_SUMMARY' in body and 'OTHER_USER_SUMMARY' not in body
    assert client.post('/account/ai-memory?family_id=a').status_code==400
    assert client.post('/account/ai-memory?family_id=a',data={'csrf_token':token}).status_code==302
    assert ai.user_context_stamp('a','owner-a')!=stamp
    assert ai._user_memory('a','member-a')=='OTHER_USER_SUMMARY'
    assert get_session().query(AiMemory).filter_by(user_id='owner-a',content=None).count()==2
    assert get_session().query(AiMessage).filter_by(id='old-message').count()==1
    sent=[]
    def stream(messages,**kwargs):sent.extend(messages);yield 'new answer'
    monkeypatch.setattr(ai,'_chat_complete_stream',stream)
    list(ai.chat_stream('a','owner-a','new question',persist=False))
    assert 'OWN_OLD_SUMMARY' not in str(sent) and 'OLD_PREFERENCE' not in str(sent)


def test_reset_prevents_inflight_memory_extraction_from_writing_back(client,login,monkeypatch):
    login();seed_memory()
    def model(*args,**kwargs):
        ai_memory.reset('a','owner-a')
        return '{"memory":"RESURRECTED_SUMMARY"}'
    monkeypatch.setattr(ai,'_chat_complete',model)
    ai._update_memory('a','owner-a')
    assert 'RESURRECTED' not in ai._user_memory('a','owner-a')
    assert get_session().query(AiMemory).filter_by(content='RESURRECTED_SUMMARY').count()==0


def test_reset_cancels_old_turn_and_blocks_its_result_or_nonce_replay(client,login,monkeypatch,app):
    login();seed_memory()
    with app.test_request_context():
        turn,_=ai_turns.begin('a','owner-a','memory-old-turn','old question')
        old_stamp=turn.context_stamp
    ai_memory.reset('a','owner-a')
    sent=[]
    def stream(*args,**kwargs):sent.append(True);yield 'must not be sent'
    monkeypatch.setattr(ai,'_chat_complete_stream',stream)
    with pytest.raises(ai.AIError):list(ai.chat_stream('a','owner-a','old question',persist=False,expected_stamp=old_stamp))
    monkeypatch.setattr(ai,'ai_enabled',lambda:True)
    response=client.post('/f/a/ask/stream',json={'message':'old question','request_id':'memory-old-turn'})
    assert response.status_code==400 and response.json['status']=='outdated'
    assert not sent


def test_reset_during_stream_does_not_publish_old_answer(client,login,monkeypatch):
    login();seed_memory()
    monkeypatch.setattr(ai,'ai_enabled',lambda:True)
    def stream(*args,**kwargs):
        yield 'first part'
        ai_memory.reset('a','owner-a')
        yield 'second part'
    monkeypatch.setattr(ai,'_chat_complete_stream',stream)
    response=client.post('/f/a/ask/stream',json={'message':'test','request_id':'memory-during-stream'},buffered=True)
    assert 'error' in response.get_data(as_text=True)
    assert get_session().query(models.AiTurn).one().status!='succeeded'
    assert get_session().query(AiMessage).filter_by(role='assistant').count()==0


def test_memory_page_keeps_family_and_membership_boundaries(client,login):
    login();assert client.get('/account/ai-memory?family_id=b').status_code==404
    s=get_session();s.query(FamilyMember).filter_by(id='ma').update({FamilyMember.del_flag:1});s.commit()
    assert client.get('/account/ai-memory?family_id=a').status_code==404


def test_family_context_queries_are_bounded_as_story_count_grows(app):
    s=get_session()
    for index in range(120):
        s.add(Interview(id='bulk-%s'%index,family_id='a',publish_status='published',visibility='public'))
        s.add(Draft(id='bulk-draft-%s'%index,interview_id='bulk-%s'%index,is_current=True,version=1,content='text'))
    s.commit();queries=[]
    def count(*args):queries.append(True)
    event.listen(models._engine,'before_cursor_execute',count)
    try:ai.context_stamp('a')
    finally:event.remove(models._engine,'before_cursor_execute',count)
    assert len(queries)<=6
