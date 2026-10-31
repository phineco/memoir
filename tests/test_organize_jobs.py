import datetime

import pytest
from werkzeug.exceptions import HTTPException

import organize_jobs as jobs
import organizing
from models import FamilyMember, OrganizeRecord, OrganizeTask, get_session
from reporting import local_now


def setup(app):
    app.config.update(ORGANIZE_ENABLED=True, INAPP_AI_DATA_APPROVED=True, DEEPSEEK_API_KEY='test-only')
    return organizing.create(get_session(), 'a', 'member-a', {'content': '原始回忆。'}).id


def test_idempotency_and_success_query_do_not_regenerate(app):
    rid = setup(app)
    with app.app_context():
        task = jobs.begin('a', 'member-a', rid, 1, 'request-1', True)
        tid = task.id
        assert jobs.begin('a', 'member-a', rid, 1, 'request-2', True).id == tid
        calls = []
        assert jobs.run_one(lambda payload: (calls.append(payload['content']) or {'title': '回忆', 'body': 'Result', 'quotes': [], 'verification': [], 'timeline': [], 'people': [], 'period': None}, {'tokens': 5}))
        assert calls == ['原始回忆。']
        assert jobs.begin('a', 'member-a', rid, 1, 'request-3', True).id == tid
        assert get_session().get(OrganizeTask, tid).status == 'succeeded'


@pytest.mark.parametrize('action', ['cancel', 'change', 'remove', 'delete'])
def test_late_result_cannot_replace_cancelled_or_changed_material(app, action):
    rid = setup(app)
    with app.app_context():
        tid = jobs.begin('a', 'member-a', rid, 1, 'request-1', True).id
        def provider(payload):
            s = get_session()
            if action == 'cancel':
                jobs.cancel('a', 'member-a', rid, tid)
            elif action == 'change':
                organizing.update(s, 'a', 'member-a', rid, 1, {'content': 'New version'})
            elif action == 'remove':
                s.get(FamilyMember, 'member').del_flag = 1
                s.commit()
            else:
                organizing.delete(s, 'a', 'member-a', rid)
            return {'body': 'Must not be current'}, {}
        jobs.run_one(provider)
        task = get_session().get(OrganizeTask, tid)
        assert task.status in ('cancelled', 'outdated') and task.result is None


def test_expired_attempt_is_unknown_and_never_automatically_replayed(app):
    rid = setup(app)
    with app.app_context():
        tid = jobs.begin('a', 'member-a', rid, 1, 'request-1', True).id
        s = get_session()
        task = s.get(OrganizeTask, tid)
        task.status = 'running'
        task.lease_until = local_now() - datetime.timedelta(seconds=1)
        s.commit()
        calls = []
        jobs.run_one(lambda payload: calls.append(payload))
        assert not calls and s.get(OrganizeTask, tid).status == 'uncertain'


def test_disabled_and_daily_limit_keep_sources(app):
    rid = setup(app)
    with app.app_context():
        app.config['ORGANIZE_ENABLED'] = False
        with pytest.raises(HTTPException):
            jobs.begin('a', 'member-a', rid, 1, 'request-1', True)
        app.config.update(ORGANIZE_ENABLED=True, ORGANIZE_DAILY_TASKS=0)
        with pytest.raises(HTTPException) as error:
            jobs.begin('a', 'member-a', rid, 1, 'request-2', True)
        assert error.value.code == 429
        assert get_session().get(OrganizeRecord, rid).content == '原始回忆。'
