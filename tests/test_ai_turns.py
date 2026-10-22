import datetime
import pytest
import ai
import ai_turns
from models import AiMessage,AiTurn,Draft,Interview,get_session
from retrieval import retrieve


@pytest.fixture
def fake_ai(monkeypatch):
    monkeypatch.setattr(ai,'ai_enabled',lambda:True)
    monkeypatch.setattr(ai,'_update_memory',lambda *args:None)
    calls=[]
    def stream(messages,**kwargs):
        calls.append(messages);yield '根据记录 [1]，这是本地回答。'
    monkeypatch.setattr(ai,'_chat_complete_stream',stream)
    return calls


def test_duplicate_request_replays_without_provider_call(client,login,fake_ai):
    login();data={'message':'院子的事','request_id':'request-local-001'}
    first=client.post('/f/a/ask/stream',json=data,buffered=True)
    assert '[DONE]' in first.get_data(as_text=True)
    assert '[DONE]' in client.post('/f/a/ask/stream',json=data,buffered=True).get_data(as_text=True)
    assert len(fake_ai)==1
    assert get_session().query(AiTurn).one().status=='succeeded'
    assert get_session().query(AiMessage).count()==2
    assert client.post('/f/a/ask/stream',json=dict(data,message='different')).status_code==409
    result=client.get('/f/a/ask/turn/request-local-001');assert result.headers['Cache-Control']=='private, no-store'
    login('member-a');assert client.get('/f/a/ask/turn/request-local-001').status_code==404


def test_failed_attempt_retains_question_and_no_implicit_retry(client,login,fake_ai,monkeypatch):
    def fail(*args,**kwargs):
        yield '未完成的一部分'
        raise ai.AIError('simulated')
    monkeypatch.setattr(ai,'_chat_complete_stream',fail)
    login();data={'message':'这个失败问题需要恢复','request_id':'request-local-fail'}
    assert 'error' in client.post('/f/a/ask/stream',json=data,buffered=True).get_data(as_text=True)
    turn=get_session().query(AiTurn).one();assert turn.status=='failed' and turn.question==data['message']
    assert '未完成的一部分' in turn.answer
    assert client.post('/f/a/ask/stream',json=data).status_code==400
    assert '这个失败问题需要恢复' in client.get('/f/a/ask').get_data(as_text=True)


def test_running_request_cancel_and_expiration(client,login,fake_ai,app):
    login()
    with app.test_request_context():
        turn,created=ai_turns.begin('a','owner-a','request-local-pending','question')
        assert created
    assert client.post('/f/a/ask/stream',json={'request_id':'request-local-pending','message':'question'}).status_code==409
    result=client.post('/f/a/ask/turn/request-local-pending').get_json();assert result['status']=='cancelled'
    assert not fake_ai
    s=get_session();turn=s.query(AiTurn).one();turn.status='running';turn.lease_until=datetime.datetime.now()-datetime.timedelta(seconds=1);s.commit()
    assert client.get('/f/a/ask/turn/request-local-pending').get_json()['status']=='failed'


def test_full_text_retrieval_and_withdrawal_remove_sources(client,login,fake_ai):
    login();s=get_session();s.query(Draft).filter_by(id='d-public-a').one().content='<p>'+'童年的往事。'*100+'后来搬到了紫藤巷十七号。</p>';s.commit()
    sources=retrieve('a','owner-a','紫藤巷在哪里')
    assert '紫藤巷十七号' in sources[0]['excerpt']
    assert all(x['story_id']=='public-a' for x in sources)
    client.post('/f/a/ask/stream',json={'message':'紫藤巷在哪里','request_id':'request-long-text'},buffered=True)
    assert '紫藤巷十七号' in str(fake_ai[0])
    result=client.get('/f/a/ask/turn/request-long-text').get_json();assert result['sources'][0]['url']=='/f/a/story/public-a#articleBody'
    s=get_session();s.query(Interview).filter_by(id='public-a').one().visibility='private';s.commit()
    result=client.get('/f/a/ask/turn/request-long-text').get_json();assert result['status']=='outdated' and not result['sources'] and not result['answer']


def test_views_do_not_invalidate_ai_history(app):
    s=get_session();before=ai.context_stamp('a');iv=s.query(Interview).filter_by(id='public-a').one();iv.view_count=999;iv.update_date=datetime.datetime.now();s.commit()
    assert ai.context_stamp('a')==before


def test_provider_truncated_stream_closes_connection(monkeypatch):
    monkeypatch.setattr(ai,'ai_enabled',lambda:True);monkeypatch.setattr(ai.Config,'DEEPSEEK_API_KEY','test-only')
    class Response:
        status_code=200;closed=False
        def iter_lines(self,**kwargs):return iter(['data: {"choices":[{"delta":{"content":"partial"}}]}'])
        def close(self):self.closed=True
    response=Response();monkeypatch.setattr(ai.requests,'post',lambda *a,**k:response)
    with pytest.raises(ai.AIError):list(ai._chat_complete_stream([]))
    assert response.closed


def test_cancelled_attempt_never_starts_provider(app,fake_ai):
    with app.test_request_context():
        turn,_=ai_turns.begin('a','owner-a','never-start-local','question')
        turn.status='cancelled';get_session().commit()
        assert any('error' in item for item in ai_turns.generate(turn,'Family'))
        assert not fake_ai


@pytest.mark.parametrize('data',[None,[],{'message':[]},{'message':'x'*2001}])
def test_invalid_question_rejected_without_request(client,login,fake_ai,data):
    login();assert client.post('/f/a/ask/stream',json=data).status_code==400
    assert get_session().query(AiTurn).count()==0 and not fake_ai
