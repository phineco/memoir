import ai
from models import AiMemory, AiMessage, Draft, Interview, get_session


def test_private_and_specific_excluded_for_all_roles(client, login):
    for uid in ('owner-a','member-a'):
        login(uid)
        text=ai.family_knowledge('a', uid)
        assert 'content-public-a' in text
        for secret in ('content-private-a','quote-private-a','content-specific-a','quote-specific-a'):
            assert secret not in text
        data=client.get('/api/weekly-report?family_id=a').get_json()
        assert {row['id'] for row in data['stories']} == {'public-a'}


def test_legacy_history_and_memory_never_sent_to_provider(app, monkeypatch):
    s=get_session()
    s.add(AiMessage(id='legacy-secret',family_id='a',user_id='owner-a',role='assistant',content='LEGACY-PRIVATE'))
    s.add(AiMemory(id='legacy-memory',family_id='a',user_id='owner-a',memory_key='profile',content='LEGACY-PRIVATE'))
    s.commit();sent=[]
    monkeypatch.setattr(ai,'_chat_complete',lambda messages,**kw:(sent.append(str(messages)) or '本地回答'))
    monkeypatch.setattr(ai,'_update_memory',lambda *args:None)
    ai.chat('a','owner-a','question')
    assert all('LEGACY-PRIVATE' not in text and 'quote-private-a' not in text for text in sent)


def test_withdrawn_or_revised_story_invalidates_derived_context(app):
    s=get_session();stamp=ai.context_stamp('a')
    s.add(AiMemory(id='current-memory',family_id='a',user_id='owner-a',memory_key=stamp,content='DERIVED-PUBLIC'))
    s.commit();assert ai._user_memory('a','owner-a')=='DERIVED-PUBLIC'
    s.query(Interview).filter_by(id='public-a').one().visibility='private';s.commit()
    assert ai.context_stamp('a')!=stamp
    assert ai._user_memory('a','owner-a')!='DERIVED-PUBLIC'
    s.query(Interview).filter_by(id='public-a').one().visibility='public'
    s.query(Draft).filter_by(id='d-public-a').one().content='a corrected version';s.commit()
    assert ai.context_stamp('a')!=stamp
