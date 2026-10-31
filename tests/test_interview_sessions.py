import pytest
from werkzeug.exceptions import HTTPException

import interviewing
from models import InterviewSession, get_session, FamilyMember


def test_session_idempotency_pause_and_membership(app):
    s = get_session()
    row = interviewing.start(s, 'a', 'member-a', {'recording_mode': 'accompany', 'narrator_label': '妈妈'}, 'interview-1')
    sid = row.id
    assert interviewing.start(s, 'a', 'member-a', {}, 'interview-1').id == sid
    assert s.query(InterviewSession).count() == 1 and row.narrator_id is None
    interviewing.pause(s, 'a', 'member-a', sid, 1)
    assert row.state == 'paused'
    interviewing.pause(s, 'a', 'member-a', sid, 2, True)
    assert row.state == 'active'
    with pytest.raises(HTTPException): interviewing.pause(s, 'a', 'member-a', sid, 2)
    s.rollback()
    with pytest.raises(HTTPException): interviewing.owned(s, 'a', 'owner-a', sid)
    s.get(FamilyMember, 'member').del_flag = 1; s.commit()
    with pytest.raises(HTTPException): interviewing.owned(s, 'a', 'member-a', sid)


def test_interview_pages_and_account_entry(client, login):
    login('member-a')
    html = client.get('/f/a/interview/new').get_data(as_text=True)
    import re
    data = {k: re.search(r'name="'+k+r'" value="([^"]+)"',html)[1] for k in ('csrf_token','nonce')}
    response = client.post('/f/a/interview/new',data=dict(data, topic='work', recording_mode='self'))
    assert response.status_code == 302
    path = response.location
    assert '第一次工作' in client.get(path).get_data(as_text=True)
    assert client.get('/account/interviews').status_code == 200
    login('owner-a')
    assert client.get(path).status_code == 404
    assert get_session().query(InterviewSession).one().id not in client.get('/account/interviews').get_data(as_text=True)
