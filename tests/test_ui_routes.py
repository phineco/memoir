import pytest

from models import FamilyMember, get_session


def test_management_keeps_admin_boundary(client, login):
    login('member-a')
    assert client.get('/f/a/more').status_code == 200
    assert client.get('/f/a/manage').status_code == 403
    assert client.get('/f/b/more').status_code == 404
    login('owner-a')
    assert client.get('/f/a/manage').status_code == 200
    assert '开通并加入本家庭' not in client.get('/f/a').get_data(as_text=True)
    response = client.post('/f/a/members/create-account', data={})
    assert response.location.endswith('/f/a/manage/accounts')
    assert '请填写家人姓名' in client.get(response.location).get_data(as_text=True)


def test_existing_draft_editor_handles_loaded_form_dict(client, login):
    login('owner-a')
    response = client.get('/f/a/story/draft-a/edit')
    assert response.status_code == 200
    assert 'content-draft-a' in response.get_data(as_text=True)


@pytest.mark.parametrize('section', ['', '/accounts', '/invites', '/tools'])
def test_management_sections_preserve_family_and_admin_boundaries(client, login, section):
    login('member-a')
    assert client.get('/f/a/manage'+section).status_code == 403
    login('owner-a')
    html = client.get('/f/a/manage'+section)
    assert html.status_code == 200
    assert 'aria-label="家庭管理分类"' in html.get_data(as_text=True)
    assert client.get('/f/b/manage'+section).status_code == 404
    assert client.get('/f/a/manage/unknown').status_code == 404


def test_management_separates_tasks_and_preserves_one_time_results(client, login):
    login()
    response = client.post('/f/a/members/create-account', data={
        'real_name':'New Relative','phone':'13800001234','password':'test-only-password'})
    assert response.location.endswith('/manage/accounts')
    for path in ['/f/a/manage', '/f/a/manage/tools', '/f/a/manage/invites']:
        html = client.get(path).get_data(as_text=True)
        assert '账号已开通' not in html and 'test-only-password' not in html
        assert 'name="real_name"' not in html
    html = client.get(response.location).get_data(as_text=True)
    assert '账号已开通' in html and 'test-only-password' in html
    assert '账号已开通' not in client.get(response.location).get_data(as_text=True)


def test_reset_errors_and_results_stay_with_members(client, login):
    login()
    response = client.post('/f/a/members/member/reset-password',data={'new_password':'x'})
    assert response.location.endswith('/f/a/manage')
    assert '新密码至少 6 位' not in client.get('/f/a/manage/accounts').get_data(as_text=True)
    assert '新密码至少 6 位' in client.get(response.location).get_data(as_text=True)
    response = client.post('/f/a/members/member/reset-password',data={'new_password':'new-test-password'})
    assert '密码已重置' not in client.get('/f/a/manage/tools').get_data(as_text=True)
    html = client.get(response.location).get_data(as_text=True)
    assert '密码已重置' in html and 'new-test-password' in html
    assert '密码已重置' not in client.get(response.location).get_data(as_text=True)


def test_results_are_not_consumed_or_shown_in_another_family(client, login):
    login()
    s=get_session()
    s.add(FamilyMember(id='owner-a-in-b',family_id='b',user_id='owner-a',role='admin'))
    s.commit()
    client.post('/f/a/members/create-account',data={
        'real_name':'Only Family A','phone':'13800004321','password':'family-a-password'})
    assert 'family-a-password' not in client.get('/f/b/manage/accounts').get_data(as_text=True)
    assert 'family-a-password' in client.get('/f/a/manage/accounts').get_data(as_text=True)


def test_admin_controls_match_existing_permissions(client, login):
    s=get_session()
    s.add(FamilyMember(id='admin-a',family_id='a',user_id='outsider',role='admin'))
    s.commit()
    login('outsider')
    html=client.get('/f/a/manage').get_data(as_text=True)
    assert '/f/a/members/member/reset-password' in html
    assert '/f/a/members/ma/reset-password' not in html
    assert '/f/a/members/admin-a/reset-password' not in html
    assert '/remove' not in html and 'name="login_id"' not in html
    assert client.post('/f/a/members/ma/reset-password',data={'new_password':'test-only'}).status_code == 403
    assert client.post('/f/a/members/member/remove').status_code == 403
