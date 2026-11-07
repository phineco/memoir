from urllib.parse import urlencode

import pytest
from werkzeug.security import generate_password_hash

from models import User, get_session


@pytest.fixture
def password_login(app):
    app.config['EASY_ENABLED'] = True
    s = get_session()
    s.get(User, 'member-a').password_hash = generate_password_hash('test-only-password')
    s.commit()
    return {'phone': 'member-a', 'password': 'test-only-password'}


@pytest.mark.parametrize('target', ['/easy/', '/easy/records/', '/easy/no-longer-exists', '/easy/login'])
def test_easy_login_never_strands_user_on_invalid_return(client, password_login, target):
    result = client.post('/easy/login?' + urlencode({'next': target}), data=password_login)
    assert result.status_code == 302
    final = client.get(result.location, follow_redirects=True)
    assert final.status_code == 200
    assert 'easy-body' in final.get_data(as_text=True)


@pytest.mark.parametrize('target', ['/easy', '/easy/records', '/easy/settings', '/easy?ask=1', '/easy/listen?page=1'])
def test_easy_login_preserves_valid_destination(client, password_login, target):
    result = client.post('/easy/login?' + urlencode({'next': target}), data=password_login)
    assert result.location == target
    assert client.get(result.location).status_code == 200


def test_failed_easy_login_does_not_redirect_or_authenticate(client, password_login):
    result = client.post('/easy/login?next=/easy/no-longer-exists', data={**password_login, 'password': 'wrong'})
    assert result.status_code == 200
    assert '登录名或密码不正确' in result.get_data(as_text=True)
    with client.session_transaction() as session:
        assert 'user_id' not in session


def test_direct_trailing_slash_entry_works_after_authentication(client, password_login):
    client.post('/easy/login', data=password_login)
    assert client.get('/easy/', follow_redirects=True).status_code == 200


@pytest.mark.parametrize('target', ['https://bad.invalid/', '//bad.invalid/', '/easy\\evil', '/easy\n', '/'])
def test_easy_login_rejects_unsafe_or_foreign_targets(client, password_login, target):
    assert client.post('/easy/login?' + urlencode({'next': target}), data=password_login).status_code == 400


def test_easy_login_keeps_family_boundary_and_feature_gate(app, client, password_login):
    result = client.post('/easy/login?next=/easy/f/b/interview/missing', data=password_login)
    assert client.get(result.location).status_code == 404
    app.config['EASY_ENABLED'] = False
    assert client.get('/easy').status_code == 404


@pytest.mark.parametrize('target', ['/easy/', '/easy/unknown', '/easy/records/'])
def test_sms_login_uses_same_safe_return(client, password_login, monkeypatch, target):
    import sms
    s = get_session()
    s.get(User, 'member-a').phone = '13800000000'
    s.commit()
    monkeypatch.setattr(sms, 'verify_code', lambda phone, code, purpose: None)
    result = client.post('/easy/login?' + urlencode({'next': target}), data={
        'login_mode': 'sms', 'phone': '13800000000', 'code': '123456'})
    assert result.status_code == 302
    assert client.get(result.location, follow_redirects=True).status_code == 200



def test_trailing_slash_keeps_explicit_family(client, password_login):
    client.post('/easy/login', data=password_login)
    result = client.get('/easy/?family_id=a')
    assert result.location == '/easy?family_id=a'
    assert client.get(result.location).status_code == 200
