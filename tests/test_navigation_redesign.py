import re
from html import unescape

import pytest

from models import FamilyMember, Person, get_session
from navigation import safe_return


@pytest.mark.parametrize('path,active', [
    ('/f/a', '家人'), ('/f/a/person/pa', '家人'), ('/f/a/tree/pa/edit', '家人'),
    ('/f/a/manage', '家人'), ('/f/a/stories', '故事'), ('/f/a/write', '故事'),
    ('/f/a/story/public-a', '故事'), ('/f/a/album', '相册'),
    ('/f/a/album/upload', '相册'), ('/f/a/ask', '更多'), ('/f/a/more', '更多'),
    ('/guide?family_id=a', None), ('/account?family_id=a', None),
    ('/account/voices?family_id=a', None),
])
def test_four_navigation_groups_and_personal_pages(client, login, path, active):
    login()
    response = client.get(path)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    nav = re.search(r'<nav class="navlinks".*?</nav>', html, re.S)[0]
    assert re.findall(r'>([^<]+)</a>', nav) == ['家人', '故事', '相册', '更多']
    current = re.findall(r'aria-current="page">([^<]+)</a>', nav)
    assert current == ([active] if active else [])
    assert 'Beta Secret Family' not in html


def test_tree_keeps_multiple_roots_orphans_and_cycles_without_rewriting(client, login):
    s = get_session()
    s.add_all([
        Person(id='root-two', family_id='a', name='Second root', parent_id='0'),
        Person(id='orphan', family_id='a', name='Orphan', parent_id='missing'),
        Person(id='cycle-one', family_id='a', name='Cycle one', parent_id='cycle-two'),
        Person(id='cycle-two', family_id='a', name='Cycle two', parent_id='cycle-one'),
    ])
    s.commit()
    login()
    from views import _build_tree
    with client.application.test_request_context():
        tree = _build_tree('a')
    found = []
    def walk(node):
        if node.get('person_id'): found.append(node['person_id'])
        for child in node.get('children', []):walk(child)
    walk(tree)
    assert set(found) == {'pa','root-two','orphan','cycle-one','cycle-two'}
    assert len(found) == len(set(found))
    assert s.get(Person,'orphan').parent_id == 'missing'
    body = client.get('/f/a?view=tree').get_data(as_text=True)
    assert 'advanced-section' not in body and 'family-tree-data' in body
    assert client.get('/f/a?view=bad').status_code == 400
    assert 'Alpha Person' in client.get('/f/a?q=Alpha').get_data(as_text=True)


def test_person_return_preserves_list_and_cannot_redirect_away(client, login):
    login()
    html = unescape(client.get('/f/a?view=list&q=Alpha').get_data(as_text=True))
    assert 'return_to=' in html
    response = client.get('/f/a/person/pa',query_string={'return_to':'/f/a?view=tree'})
    assert 'data-restore-list href="/f/a?view=tree"' in response.get_data(as_text=True)
    for value in ['https://bad.test','//bad.test','http://[','/f/b','/logout','/f/a/manage','/account?family_id=b','/f/a\\evil']:
        assert safe_return(value,'a') is None
    assert safe_return('/account/stories?kind=own','a')
    assert safe_return('/f/a/album?uploader=user%3Aowner-a&page=2','a')


def test_switch_targets_family_people_and_revocation_removes_choices(client, login):
    login()
    html = client.get('/?switch=1').get_data(as_text=True)
    assert 'data-family-choice="a" href="/f/a"' in html
    get_session().get(FamilyMember,'ma').del_flag=1
    get_session().commit()
    body = client.get('/account').get_data(as_text=True)
    assert 'Alpha Family' not in body
