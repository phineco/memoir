import pytest

from models import Draft, VerificationItem, get_session
from test_sync_people import sync


@pytest.mark.parametrize('bad', [
    {'kind': 'draft', 'interview_client_id': 'missing', 'draft': 'Missing', 'base_version': 1, 'revision_reason': 'Check'},
    {'kind': 'verify', 'interview_id': 'public-a', 'item_id': 'missing', 'action': 'confirm'},
    {'kind': 'verify', 'interview_id': 'public-a', 'item_id': 'v-public-a', 'action': 'unknown'},
    {'kind': 'draft', 'interview_id': 'public-a', 'draft': ''},
    {'kind': 'person', 'name': 'Unknown person', 'full_name': 'New name'},
    {'kind': 'unknown'},
])
def test_unmatched_or_invalid_revision_rolls_back_entire_packet(client, login, bad):
    login()
    first = {'kind': 'draft', 'interview_id': 'public-a', 'draft': '<p>Valid</p>',
             'base_version': 1, 'revision_reason': 'Checked source'}
    response = sync(client, 'revision_sync', {'revisions': [first, bad]}, 'atomic-sync')
    assert response.status_code == 400
    s = get_session()
    assert s.get(Draft, 'd-public-a').is_current
    assert s.query(Draft).filter_by(interview_id='public-a').count() == 1
    # The original clientId is free after failure; the corrected whole packet is safe.
    assert sync(client, 'revision_sync', {'revisions': [first]}, 'atomic-sync').json['applied']
    assert sync(client, 'revision_sync', {'revisions': [first]}, 'atomic-sync').json['applied'] is False


def test_repeated_verification_text_requires_item_id(client, login):
    login()
    s = get_session()
    s.add(VerificationItem(id='duplicate-check', interview_id='public-a', text='verify-public-a', status='pending'))
    s.commit()
    payload = {'interview_id': 'public-a', 'item_text': 'verify-public-a', 'status': 'verified'}
    assert sync(client, 'verification_update', payload).status_code == 400
    payload['item_id'] = 'duplicate-check'
    assert sync(client, 'verification_update', payload).json['applied']
    assert s.get(VerificationItem, 'v-public-a').status == 'pending'
    assert s.get(VerificationItem, 'duplicate-check').status == 'resolved'


def test_invalid_explicit_item_id_never_falls_back_to_different_item(client, login):
    login()
    assert sync(client, 'verification_update', {'interview_id': 'public-a', 'item_id': 'v-private-a',
        'item_text': 'verify-public-a', 'status': 'verified'}).status_code == 400
    assert get_session().get(VerificationItem, 'v-public-a').status == 'pending'
