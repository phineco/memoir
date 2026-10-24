from uuid import uuid4

import pytest

from models import Draft, SyncLog, get_session


def revise(client, version=1, reason='Checked original source', content='<p>Revised</p>', key=None):
    return client.post('/api/sync', json={'family_id': 'a', 'packet': {
        'type': 'revision_sync', 'clientId': key or uuid4().hex, 'payload': {'revisions': [
            {'kind': 'draft', 'interview_id': 'public-a', 'draft': content,
             'base_version': version, 'revision_reason': reason}]}}})


@pytest.mark.parametrize('version', [None, True, -1, 1.5, '1.0', 0, 2])
def test_missing_invalid_or_stale_base_does_not_change_story(client, login, version):
    login()
    assert revise(client, version=version).status_code == 400
    s = get_session()
    assert s.query(Draft).filter_by(interview_id='public-a').count() == 1
    assert s.get(Draft, 'd-public-a').is_current


def test_sync_and_web_share_version_guard_and_retain_reason(client, login):
    login()
    assert revise(client, key='v2').json['applied']
    s = get_session()
    current = s.query(Draft).filter_by(interview_id='public-a', is_current=True).one()
    assert current.version == 2 and current.remarks == 'Checked original source'
    assert revise(client, content='Old copy').status_code == 400
    assert client.post('/f/a/story/public-a/edit', data={
        'topic': 'Old', 'content': 'Old web copy', 'base_version': '1',
        'revision_reason': 'Old browser tab'}).status_code == 409
    assert client.post('/f/a/story/public-a/edit', data={
        'topic': 'New', 'content': 'Current web edit', 'base_version': '2',
        'revision_reason': 'Checked again'}).status_code == 302
    assert revise(client, version=2).status_code == 400
    assert get_session().query(Draft).filter_by(interview_id='public-a', is_current=True).one().version == 3


def test_failure_can_be_corrected_with_same_client_id(client, login):
    login()
    assert revise(client, reason='', key='retry-revision').status_code == 400
    assert revise(client, key='retry-revision').json['applied']
    assert revise(client, key='retry-revision').json['applied'] is False
    assert get_session().query(SyncLog).filter_by(client_id='retry-revision').count() == 1


def test_stale_second_revision_rolls_back_first_in_same_packet(client, login):
    login()
    data = {'family_id': 'a', 'packet': {'type': 'revision_sync', 'clientId': 'atomic-versions',
        'payload': {'revisions': [
            {'kind': 'draft', 'interview_id': 'public-a', 'draft': 'One', 'base_version': 1, 'revision_reason': 'One'},
            {'kind': 'draft', 'interview_id': 'private-a', 'draft': 'Two', 'base_version': 0, 'revision_reason': 'Two'}]}}}
    assert client.post('/api/sync', json=data).status_code == 400
    assert get_session().get(Draft, 'd-public-a').is_current
    assert get_session().query(Draft).filter_by(interview_id='public-a').count() == 1
