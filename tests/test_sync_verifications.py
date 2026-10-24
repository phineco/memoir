import sqlite3

import pytest

from migrate import run_migrations
from models import VerificationItem, get_session
from test_migrations import old_database
from test_sync_people import sync


@pytest.mark.parametrize('status', ['verified', 'resolved', 'corrected'])
def test_resolved_states_have_consistent_ui_and_real_resolution_time(client, login, status):
    login()
    assert sync(client, 'verification_update', {'interview_id': 'public-a', 'item_id': 'v-public-a',
                'status': status, 'correction': 'Checked year'}).json['applied']
    item = get_session().get(VerificationItem, 'v-public-a')
    assert item.status == 'resolved' and item.correction == 'Checked year'
    assert item.resolved_at is not None
    assert '✅ 「verify-public-a」' in client.get('/f/a/story/public-a').get_data(as_text=True)


def test_reopening_clears_resolution_time(client, login):
    login()
    payload = {'interview_id': 'public-a', 'item_id': 'v-public-a', 'status': 'verified'}
    assert sync(client, 'verification_update', payload).json['applied']
    payload['status'] = 'pending'
    assert sync(client, 'verification_update', payload).json['applied']
    assert get_session().get(VerificationItem, 'v-public-a').resolved_at is None


@pytest.mark.parametrize('status,correction', [('corrected', ''), ('corrected', None), ('nonsense', 'Year')])
def test_invalid_status_or_empty_correction_is_rejected(client, login, status, correction):
    login()
    assert sync(client, 'verification_update', {'interview_id': 'public-a', 'item_id': 'v-public-a',
                'status': status, 'correction': correction}).status_code == 400
    assert get_session().get(VerificationItem, 'v-public-a').status == 'pending'


def test_revision_correction_uses_same_rules(client, login):
    login()
    item = {'kind': 'verify', 'interview_id': 'public-a', 'item_id': 'v-public-a', 'action': 'correct'}
    assert sync(client, 'revision_sync', {'revisions': [item]}).status_code == 400
    item['correction'] = 'Checked source'
    assert sync(client, 'revision_sync', {'revisions': [item]}).json['applied']
    assert get_session().get(VerificationItem, 'v-public-a').status == 'resolved'
    assert get_session().get(VerificationItem, 'v-public-a').resolved_at is not None


def test_legacy_corrected_migration_preserves_unknown_resolution_time(tmp_path):
    path = old_database(tmp_path)
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO verification_items VALUES ('legacy-corrected', 'corrected')")
        db.execute("INSERT INTO verification_items VALUES ('legacy-pending', 'pending')")
    url = 'sqlite:///' + str(path)
    run_migrations(url)
    run_migrations(url)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT status,resolved_at FROM verification_items WHERE id='legacy-corrected'").fetchone() == ('resolved', None)
        assert db.execute("SELECT status,resolved_at FROM verification_items WHERE id='legacy-pending'").fetchone() == ('pending', None)
