import json
from uuid import uuid4

import pytest

from models import Interview, NewPerson, Person, PersonIdMap, SyncLog, WritingPlan, get_session


def sync(client, kind, payload, key=None):
    return client.post('/api/sync', json={'family_id': 'a', 'packet': {
        'type': kind, 'clientId': key or uuid4().hex, 'payload': payload}})


def test_new_person_requires_real_person_then_new_mapping_packet(client, login):
    login()
    tree = {'persons': [{'id': 'p90', 'fullName': 'New Relative'}]}
    assert sync(client, 'tree_upsert', tree, 'first-tree').json['applied']
    s = get_session()
    assert s.query(NewPerson).filter_by(name='New Relative').count() == 1
    assert not s.query(PersonIdMap).filter_by(skill_id='p90').count()
    body = {'topic': 'New story', 'subject_person_id': 'p90', 'draft': 'Synthetic'}
    assert sync(client, 'interview_upsert', body, 'new-story').status_code == 400
    assert not s.query(Interview).filter_by(topic='New story').count()
    s.add(Person(id='site-new', family_id='a', name='New Relative'))
    s.commit()
    assert sync(client, 'tree_upsert', tree, 'first-tree').json['applied'] is False
    assert sync(client, 'interview_upsert', body, 'new-story').status_code == 400
    assert sync(client, 'tree_upsert', tree, 'mapping-tree').json['applied']
    assert sync(client, 'interview_upsert', body, 'new-story').json['applied']
    assert s.query(Interview).filter_by(topic='New story').one().person_id == 'site-new'
    assert s.query(Interview).filter_by(topic='New story').count() == 1


@pytest.mark.parametrize('key', ['subject_person_id', 'narrator_person_id', 'related_persons'])
def test_unmatched_explicit_reference_rejects_without_silent_loss(client, login, key):
    login()
    payload = {'topic': 'Unmatched', 'draft': 'Body', key: 'p-unknown'}
    if key == 'related_persons':
        payload[key] = [{'person_id': 'p-unknown'}]
    assert sync(client, 'interview_upsert', payload).status_code == 400
    assert not get_session().query(Interview).filter_by(topic='Unmatched').count()


def test_unknown_narrator_without_claimed_id_remains_honest(client, login):
    login()
    assert sync(client, 'interview_upsert', {'topic': 'Unknown narrator', 'draft': 'Body',
                                            'narrator_name': 'Not yet identified'}).json['applied']
    iv = get_session().query(Interview).filter_by(topic='Unknown narrator').one()
    assert iv.narrator_person_id is None and 'Not yet identified' in iv.remarks


def test_plan_site_id_has_explicit_namespace(client, login):
    s = get_session()
    s.add(WritingPlan(id='plan-a', family_id='a', title='Plan', status='active', items=json.dumps([
        {'person_id': 'pa', 'person_name': 'Alpha Person', 'status': 'pending'}])))
    s.commit()
    login()
    returned = client.get('/api/writing-plan?family_id=a').json['plan']['items'][0]['person_id']
    assert sync(client, 'plan_progress', {'plan_id': 'plan-a', 'items': [
        {'person_id': returned, 'status': 'done'}]}).status_code == 400
    assert sync(client, 'plan_progress', {'plan_id': 'plan-a', 'items': [
        {'site_person_id': returned, 'status': 'done'}]}).json['applied']
    assert json.loads(s.get(WritingPlan, 'plan-a').items)[0]['status'] == 'done'


def test_explicit_site_mapping_is_family_scoped_and_immutable(client, login):
    login()
    def tree(site_id):
        return {'persons': [{'id': 'p01', 'site_person_id': site_id, 'fullName': 'Alpha Person'}]}
    assert sync(client, 'tree_upsert', tree('pb')).status_code == 400
    assert sync(client, 'tree_upsert', tree('pa')).json['applied']
    s = get_session()
    s.add(Person(id='other-site', family_id='a', name='Alpha Person'))
    s.commit()
    assert sync(client, 'tree_upsert', tree('other-site')).status_code == 400
    s.get(Person, 'pa').del_flag = 1
    s.commit()
    assert sync(client, 'tree_upsert', tree('other-site')).status_code == 400
    assert s.query(PersonIdMap).filter_by(skill_id='p01').one().person_id == 'pa'
