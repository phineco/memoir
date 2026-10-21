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
