import json

import pytest

from models import Interview, NewPerson, get_session
from test_sync_people import sync


def new_packet(key, name):
    return {'type': 'new_person', 'version': 1, 'clientId': key, 'payload': {'name': name}}


def fenced(packet):
    return '```sync-json\n' + json.dumps(packet) + '\n```'


def test_multiple_blocks_rejected_without_importing_first(client, login):
    login()
    a, b = new_packet('packet-a', 'First Relative'), new_packet('packet-b', 'Second Relative')
    response = client.post('/f/a/sync', data={'sync_json': fenced(a) + '\n' + fenced(b)})
    assert '一次只能导入一个同步包' in response.get_data(as_text=True)
    assert get_session().query(NewPerson).count() == 0
    for packet in (a, b):
        assert client.post('/f/a/sync', data={'sync_json': fenced(packet)}).status_code == 200
    assert get_session().query(NewPerson).count() == 2


@pytest.mark.parametrize('wrapper', [lambda p: json.dumps([p]), lambda p: json.dumps(p) + json.dumps(p)])
def test_batch_array_and_concatenated_objects_never_partially_import(client, login, wrapper):
    login()
    client.post('/f/a/sync', data={'sync_json': wrapper(new_packet('bad-batch', 'Candidate'))})
    assert get_session().query(NewPerson).count() == 0


@pytest.mark.parametrize('version', [True, 0, 999, '1', None])
def test_unsupported_protocol_version_is_rejected(client, login, version):
    login()
    packet = new_packet('bad-version', 'Candidate')
    packet['version'] = version
    response = client.post('/api/sync', json={'family_id': 'a', 'packet': packet})
    assert response.status_code == 400
    assert get_session().query(NewPerson).count() == 0


def test_single_legacy_packet_without_version_remains_compatible(client, login):
    login()
    assert sync(client, 'new_person', {'name': 'Legacy candidate'}).json['applied']


@pytest.mark.parametrize('unsupported', [{'visibility': 'private'}, {'publish_status': 'draft'}, {'viewer_ids': ['owner-a']}])
def test_unsupported_privacy_request_is_rejected_instead_of_published(client, login, unsupported):
    login()
    payload = dict(topic='Intended private draft', draft='<p>Synthetic private text</p>', **unsupported)
    assert sync(client, 'interview_upsert', payload).status_code == 400
    assert not get_session().query(Interview).filter_by(topic='Intended private draft').count()
