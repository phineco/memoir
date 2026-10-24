from uuid import uuid4

import pytest

from models import (Draft, FamilyMember, Interview, InterviewViewer, SyncLog,
                    VerificationItem, get_session)


def packet(operation, story_id):
    if operation == 'verification_update':
        return {'type': operation, 'clientId': uuid4().hex, 'payload': {
            'interview_id': story_id, 'item_id': 'check', 'status': 'verified'}}
    revision = {'kind': operation, 'interview_id': story_id,
                'draft': '<p>Revised</p>', 'action': 'correct', 'item_id': 'check',
                'correction': 'Checked year'}
    return {'type': 'revision_sync', 'clientId': uuid4().hex,
            'payload': {'revisions': [revision]}}


def seed_story(author='member-a', visibility='private', published='published'):
    s = get_session()
    s.add(Interview(id='target', family_id='a', author_id=author,
                    topic='Target', visibility=visibility, publish_status=published))
    s.add(Draft(id='target-v1', interview_id='target', version=1,
                is_current=True, content='Original'))
    s.add(VerificationItem(id='check', interview_id='target', text='Year?', status='pending'))
    s.commit()


@pytest.mark.parametrize('operation', ['draft', 'verify', 'verification_update'])
@pytest.mark.parametrize('visibility', ['private', 'specific', 'public'])
def test_admin_cannot_modify_another_authors_story(client, login, operation, visibility):
    seed_story(visibility=visibility)
    # Even designated read access never grants authoring/curation permission.
    s = get_session()
    s.add(InterviewViewer(id='admin-view', interview_id='target', user_id='owner-a'))
    s.commit()
    login()
    response = client.post('/api/sync', json={'family_id': 'a', 'packet': packet(operation, 'target')})
    assert response.status_code == 400
    assert '可整理' in response.json['error']
    assert get_session().get(Draft, 'target-v1').is_current
    assert get_session().get(VerificationItem, 'check').status == 'pending'
    assert not get_session().query(SyncLog).filter_by(status='ok').count()


@pytest.mark.parametrize('operation', ['draft', 'verify', 'verification_update'])
@pytest.mark.parametrize('author,visibility', [('owner-a', 'private'), (None, 'public')])
def test_author_and_authorless_public_curation_still_work(client, login, operation, author, visibility):
    seed_story(author, visibility)
    login()
    assert client.post('/api/sync', json={'family_id': 'a', 'packet': packet(operation, 'target')}).json['applied']


def test_denied_revision_rolls_back_earlier_items(client, login):
    seed_story()
    login()
    data = packet('draft', 'target')
    data['payload']['revisions'].insert(0, {'kind': 'draft', 'interview_id': 'public-a', 'draft': 'Allowed'})
    assert client.post('/api/sync', json={'family_id': 'a', 'packet': data}).status_code == 400
    s = get_session()
    assert s.get(Draft, 'd-public-a').is_current
    assert s.query(Draft).filter_by(interview_id='public-a').count() == 1


@pytest.mark.parametrize('user', ['member-a', 'outsider'])
def test_non_admin_sync_is_denied(client, login, user):
    login(user)
    assert client.post('/api/sync', json={'family_id': 'a', 'packet': packet('draft', 'public-a')}).status_code in (403, 404)


def test_removed_admin_cannot_write_and_cross_family_is_rejected(client, login):
    login()
    assert client.post('/api/sync', json={'family_id': 'a', 'packet': packet('draft', 'public-b')}).status_code == 400
    s = get_session()
    s.get(FamilyMember, 'ma').del_flag = 1
    s.commit()
    assert client.post('/api/sync', json={'family_id': 'a', 'packet': packet('draft', 'public-a')}).status_code == 404
