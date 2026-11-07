import json
import re

from models import Person, get_session
from views import _build_tree


def nodes(tree):
    found = {}
    stack = [tree]
    while stack:
        node = stack.pop()
        if node.get('person_id'):
            found[node['person_id']] = node
        stack.extend(node.get('children', []))
    return found


def test_tree_passes_authorized_spouse_and_parent_relationships_without_rewriting(app, client, login):
    s = get_session()
    s.get(Person, 'pa').spouse_id = 'partner'
    s.add_all([
        Person(id='partner', family_id='a', name='Partner', spouse_id='pa', parent_id='pa', sort=99),
        Person(id='child', family_id='a', name='Child', parent_id='partner'),
        Person(id='invalid-spouse', family_id='a', name='Invalid', spouse_id='pb', parent_id='pb'),
        Person(id='removed-spouse', family_id='a', name='Removed', spouse_id='pa', del_flag=1),
    ])
    s.commit()
    with app.test_request_context():
        found = nodes(_build_tree('a'))
    assert set(found) == {'pa', 'partner', 'child', 'invalid-spouse'}
    assert found['pa']['spouse_id'] == 'partner'
    assert found['partner']['parent_id'] == 'pa'
    assert found['child']['parent_id'] == 'partner'
    assert found['invalid-spouse']['spouse_id'] is None
    assert found['invalid-spouse']['parent_id'] is None
    assert s.get(Person, 'partner').parent_id == 'pa'
    assert s.get(Person, 'partner').sort == 99
    login()
    html = client.get('/f/a?view=tree').get_data(as_text=True)
    payload = re.search(r'id="family-tree-data">(.*?)</script>', html, re.S)[1]
    assert 'pb' not in json.dumps(json.loads(payload))
    assert 'tree-expand' in html
    assert 'family-tree-layout.' in html
    assert 'family-chart-0.9.0.min.' in html
    assert 'd3-7.9.0.min.' in html
    assert 'family-chart-adapter.' in html
    assert 'echarts-' not in html


def test_create_spouse_keeps_independent_parent_and_draws_reciprocal_link(client, login):
    login()
    result = client.post('/f/a/tree/add', data={
        'name': 'New Partner', 'spouse_id': 'pa', 'parent_id': '0',
        'sort': '75', 'life_status': 'unknown',
    })
    assert result.status_code == 302
    s = get_session()
    partner = s.query(Person).filter_by(name='New Partner').one()
    assert partner.parent_id == '0'
    assert partner.sort == 75
    assert partner.spouse_id == 'pa'
    assert s.get(Person, 'pa').spouse_id == partner.id
    with client.application.test_request_context():
        found = nodes(_build_tree('a'))
    assert found[partner.id]['spouse_id'] == 'pa'
    assert found['pa']['spouse_id'] == partner.id


def test_spouse_form_explains_order_and_preserves_existing_selection(client, login):
    s = get_session()
    s.get(Person, 'pa').spouse_id = 'partner'
    s.add(Person(id='partner', family_id='a', name='Partner', spouse_id='pa'))
    s.commit()
    login()
    html = client.get('/f/a/tree/pa/edit').get_data(as_text=True)
    assert '同辈排序' in html and '配偶会在家族树中同层并排' in html
    assert 'value="partner" selected' in html
    assert client.get('/f/b?view=tree').status_code == 404
    login('member-a')
    assert client.post('/f/a/tree/add', data={'name': 'No Permission'}).status_code == 403
