import re

import pytest

from models import FamilyMember, Person, User, get_session


def link_options(html):
    return re.search(r'<select name="link_user_id">(.*?)</select>', html, re.S)[1]


def test_create_lists_only_active_family_accounts(client, login):
    s = get_session()
    s.add_all([
        User(id='removed-user', username='removed-user', nickname='Removed Member'),
        User(id='deleted-user', username='deleted-user', nickname='Deleted Member', del_flag=1),
        FamilyMember(id='removed-link', family_id='a', user_id='removed-user', role='member', del_flag=1),
        FamilyMember(id='deleted-link', family_id='a', user_id='deleted-user', role='member'),
    ])
    s.commit()
    login()
    response = client.get('/f/a/tree/add')
    assert response.status_code == 200
    options = link_options(response.get_data(as_text=True))
    assert 'value="owner-a"' in options and 'value="member-a"' in options
    for identifier in ['owner-b', 'outsider', 'removed-user', 'deleted-user']:
        assert f'value="{identifier}"' not in options
    assert 'value=""' in options


def test_create_saves_account_link_immediately_and_edit_can_keep_or_clear_it(client, login):
    login()
    result = client.post('/f/a/tree/add', data={'name': 'Linked Person', 'link_user_id': 'member-a'})
    assert result.status_code == 302
    person = get_session().query(Person).filter_by(name='Linked Person').one()
    assert person.user_id == 'member-a'
    pid = person.id
    html = client.get(f'/f/a/tree/{pid}/edit').get_data(as_text=True)
    assert 'value="member-a" selected' in link_options(html)
    assert client.post(f'/f/a/tree/{pid}/edit', data={'name': 'Linked Person', 'link_user_id': 'member-a'}).status_code == 302
    assert get_session().get(Person, pid).user_id == 'member-a'
    assert client.post(f'/f/a/tree/{pid}/edit', data={'name': 'Linked Person', 'link_user_id': ''}).status_code == 302
    assert get_session().get(Person, pid).user_id is None


def test_create_account_link_is_optional(client, login):
    login()
    assert client.post('/f/a/tree/add', data={'name': 'Unlinked Person'}).status_code == 302
    assert get_session().query(Person).filter_by(name='Unlinked Person').one().user_id is None


@pytest.mark.parametrize('uid', ['owner-b', 'outsider', 'missing', 'member-a'])
def test_create_rejects_foreign_missing_or_revoked_accounts_without_saving(client, login, uid):
    if uid == 'member-a':
        s = get_session()
        s.get(FamilyMember, 'member').del_flag = 1
        s.commit()
    login()
    result = client.post('/f/a/tree/add', data={'name': 'Must Not Save', 'spouse_id': 'pa', 'link_user_id': uid})
    assert result.status_code == 400
    assert get_session().query(Person).filter_by(name='Must Not Save').count() == 0
    assert get_session().get(Person, 'pa').spouse_id is None


def test_duplicate_account_link_preserves_form_and_rolls_back_new_person_and_spouse(client, login):
    s = get_session()
    s.get(Person, 'pa').user_id = 'member-a'
    s.commit()
    login()
    result = client.post('/f/a/tree/add', data={'name': 'Duplicate Person', 'spouse_id': 'pa', 'link_user_id': 'member-a'})
    assert result.status_code == 200
    html = result.get_data(as_text=True)
    assert '该账号已关联 Alpha Person' in html
    assert 'value="member-a" selected' in link_options(html)
    assert 'value="Duplicate Person"' in html
    assert get_session().query(Person).filter_by(name='Duplicate Person').count() == 0
    assert get_session().get(Person, 'pa').spouse_id is None


@pytest.mark.parametrize('extra', [
    {'name': ''}, {'parent_id': 'missing'}, {'birth_solar_year': 'oops'}, {'spouse_id': 'missing'},
])
def test_create_errors_keep_account_choices_and_selection(client, login, extra):
    login()
    form = {'name': 'Invalid Person', 'link_user_id': 'member-a', **extra}
    response = client.post('/f/a/tree/add', data=form)
    assert response.status_code == 200
    options = link_options(response.get_data(as_text=True))
    assert 'value="owner-a"' in options and 'value="member-a" selected' in options
    assert get_session().query(Person).filter_by(name='Invalid Person').count() == 0


def test_create_link_requires_administrator(client, login):
    login('member-a')
    assert client.get('/f/a/tree/add').status_code == 403
    assert client.post('/f/a/tree/add', data={'name': 'No Permission', 'link_user_id': 'member-a'}).status_code == 403
