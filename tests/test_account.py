from html import unescape

from models import FamilyMember, Interview, get_session


def test_account_requires_login_and_keeps_family_boundary(client, login):
    assert client.get('/account').status_code == 302
    assert client.get('/account/drafts').status_code == 302
    login()
    html = client.get('/f/a/more').get_data(as_text=True)
    assert '个人中心：Alpha Owner' in html
    assert '>显示设置</a>' not in html and '我的草稿' not in html
    profile = client.get('/account?family_id=a')
    assert profile.status_code == 200
    assert '显示设置' in profile.get_data(as_text=True)
    assert '我的草稿' in profile.get_data(as_text=True)
    assert client.get('/account?family_id=b').status_code == 404
    assert client.get('/account/drafts?family_id=b').status_code == 404


def test_my_drafts_only_lists_own_drafts_in_current_memberships(client, login):
    s=get_session()
    s.add(Interview(id='own-b',family_id='b',author_id='owner-a',topic='former-family-draft',publish_status='draft'))
    s.add(Interview(id='other-author',family_id='a',author_id='member-a',topic='other-member-draft',publish_status='draft'))
    s.commit()
    login()
    html=client.get('/account/drafts').get_data(as_text=True)
    assert 'draft-a' in html
    assert 'former-family-draft' not in html and 'other-member-draft' not in html
    assert 'public-a' not in html
    member=s.query(FamilyMember).filter_by(id='ma').one();member.del_flag=1;s.commit()
    assert 'draft-a' not in client.get('/account/drafts').get_data(as_text=True)


def test_help_preserves_family_navigation_and_auth_controls(client, login):
    login()
    home=client.get('/f/a').get_data(as_text=True)
    assert '/guide?family_id=a' in home and '>帮助</a>' in home
    help_html=client.get('/guide?family_id=a').get_data(as_text=True)
    for href in ['/f/a/stories','/f/a/write','/f/a/more','/account?family_id=a']:
        assert href in home and href in help_html
    assert 'aria-label="家庭导航"' in help_html
    assert '退出' in help_html and '使用帮助' in help_html
    assert 'javascript:history.back()' not in help_html
    assert client.get('/guide?family_id=b').status_code == 404
    client.get('/logout')
    guest=client.get('/guide').get_data(as_text=True)
    assert '登录' in guest and '注册' in guest


def test_personal_voice_and_family_picker_preserve_authorized_navigation(client, login):
    login()
    account=unescape(client.get('/account?family_id=a').get_data(as_text=True))
    assert '/account/voices?family_id=a' in account
    assert '/?switch=1&family_id=a' in account
    for target in ['/account/voices?family_id=a','/?switch=1&family_id=a']:
        response=client.get(target)
        assert response.status_code==200
        body=response.get_data(as_text=True)
        assert 'aria-label="家庭导航"' in body
        for link in ['/f/a/stories','/f/a/album','/f/a/more','/f/a','/account?family_id=a','/guide?family_id=a']:
            assert f'href="{link}"' in body
        assert 'Beta Secret Family' not in body
    assert 'href="/account?family_id=a"' in client.get('/account/voices?family_id=a').get_data(as_text=True)
    # Explicit picker requests keep all choices; selecting one uses that family's own links.
    s=get_session();s.add(FamilyMember(id='second-family',family_id='b',user_id='owner-a',role='member'));s.commit()
    body=client.get('/?switch=1&family_id=a').get_data(as_text=True)
    assert 'data-family-choice="a"' in body and 'data-family-choice="b"' in body
    body=client.get('/account/voices?family_id=b').get_data(as_text=True)
    assert 'href="/f/b/stories"' in body and 'href="/f/a/stories"' not in body


def test_navigation_context_never_restores_revoked_family_access(client,login):
    login()
    assert client.get('/?switch=1&family_id=b').status_code==404
    assert client.get('/account/voices?family_id=b').status_code==404
    s=get_session();s.query(FamilyMember).filter_by(id='ma').one().del_flag=1;s.commit()
    assert client.get('/?switch=1&family_id=a').status_code==404
    assert client.get('/account/voices?family_id=a').status_code==404
    body=client.get('/account/voices').get_data(as_text=True)
    assert '我的声音授权' in body and 'Alpha Family' not in body
    assert 'aria-label="家庭导航"' not in body
