import re
import pytest

from models import PrivacyRequest,PrivacyResponse,get_session


@pytest.fixture(autouse=True)
def configured_operator(app):
    app.config['OPERATIONS_USER_IDS']=('outsider',)


def fields(response):
    return dict(re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"',response.get_data(as_text=True)))


def submit(client,details='请清理本人 AI 对话记录'):
    data=fields(client.get('/account/privacy-requests'))
    data.update(kind='ai',details=details)
    return client.post('/account/privacy-requests',data=data),data


def test_request_is_owned_idempotent_and_not_an_automatic_delete(client,login):
    login();response,data=submit(client)
    assert response.status_code==302
    assert client.post('/account/privacy-requests',data=data).location==response.location
    item=get_session().query(PrivacyRequest).one()
    assert item.status=='submitted' and item.first_response_at is None
    assert '3 个工作日' in client.get(response.location).get_data(as_text=True)
    assert client.post('/account/privacy-requests',data={**data,'details':'different'}).status_code==409
    login('member-a');assert client.get(response.location).status_code==404
    login('owner-b');assert client.get(response.location).status_code==404
    assert client.get('/operations/privacy').status_code==403


def test_only_explicit_operator_can_respond_and_completion_requires_verification(app,client,login):
    login();response,_=submit(client);path=response.location
    item=get_session().query(PrivacyRequest).one();identifier=item.id
    assert client.get('/operations/privacy/'+identifier).status_code==403
    app.config['OPERATIONS_USER_IDS']=('owner-b',)
    login('owner-b');op='/operations/privacy/'+identifier
    data=fields(client.get(op));data.update(status='completed',content='已完成核验范围内的处理')
    assert client.post(op,data=data).status_code==400
    data['verified']='yes'
    assert client.post(op,data=data).status_code==302
    item=get_session().query(PrivacyRequest).one()
    assert item.status=='completed' and item.first_response_at and item.identity_verified_at and item.resolved_at
    assert get_session().query(PrivacyResponse).one().actor_role=='operator'
    assert client.post(op,data=data).status_code==409
    login();assert '已完成核验范围内的处理' in client.get(path).get_data(as_text=True)


def test_user_supplement_cannot_fake_operator_feedback_and_old_versions_conflict(app,client,login):
    login();response,_=submit(client);path=response.location
    initial=fields(client.get(path));initial.update(content='<script>user-text</script>')
    assert client.post(path,data=initial).status_code==302
    assert get_session().query(PrivacyRequest).one().first_response_at is None
    assert client.post(path,data=initial).status_code==409
    html=client.get(path).get_data(as_text=True)
    assert '<script>user-text</script>' not in html and '&lt;script&gt;' in html
    data=fields(client.get(path));data.update(action='withdraw')
    assert client.post(path,data=data).status_code==302
    assert get_session().query(PrivacyRequest).one().status=='withdrawn'


def test_forms_require_csrf_and_do_not_expose_other_users_in_lists(client,login):
    login();assert client.post('/account/privacy-requests',data={'kind':'ai','details':'test','nonce':'valid-nonce'}).status_code==400
    response,_=submit(client,'PRIVATE_REQUEST_MARKER')
    login('member-a')
    assert 'PRIVATE_REQUEST_MARKER' not in client.get('/account/privacy-requests').get_data(as_text=True)
    assert client.post(response.location,data={'action':'withdraw'}).status_code==404


def test_submission_disabled_until_a_real_operator_is_explicitly_configured(app,client,login):
    login();app.config['OPERATIONS_USER_IDS']=()
    body=client.get('/account/privacy-requests').get_data(as_text=True)
    assert '站内申请尚未启用' in body and 'mailto:' in body
    with client.session_transaction() as state:state['_csrf']='known-test-token'
    response=client.post('/account/privacy-requests',data=dict(csrf_token='known-test-token',nonce='test-nonce',kind='ai',details='request'))
    assert response.status_code==503 and get_session().query(PrivacyRequest).count()==0
