import pytest
from werkzeug.exceptions import HTTPException

import organize_jobs as jobs
import organize_preview as preview
import organizing
from models import OrganizeTask, OrganizeRecord, get_session
from test_organize_provider import bundle, SOURCE


def create():
    return organizing.create(get_session(), 'a', 'member-a', {'content': SOURCE}).id


def test_edit_quote_becomes_summary_and_stale_preview_is_rejected(app):
    s = get_session(); rid = create()
    record = preview.manual(s, 'a', 'member-a', rid, 1, 0)
    record.preview = bundle(); s.commit()
    data = {'title': '人工标题', 'body': '人工正文', 'keep_quotes_0': 'yes', 'quote_0': '慢慢努力就好'}
    record = preview.save(s, 'a', 'member-a', rid, 1, 1, data)
    assert record.preview['quotes'][0]['kind'] == 'summary'
    assert not record.preview['timeline']
    with pytest.raises(HTTPException) as e: preview.save(s, 'a', 'member-a', rid, 1, 1, data)
    assert e.value.code == 409
    s.rollback()
    organizing.update(s, 'a', 'member-a', rid, 1, {'content': '新的回忆'})
    with pytest.raises(HTTPException): preview.save(s, 'a', 'member-a', rid, 2, 2, data)


def test_generation_cannot_overwrite_human_edit_made_while_running(app):
    rid = create()
    app.config.update(ORGANIZE_ENABLED=True, INAPP_AI_DATA_APPROVED=True, DEEPSEEK_API_KEY='test-only')
    with app.app_context():
        tid = jobs.begin('a', 'member-a', rid, 1, 'request-11', True).id
        def provider(payload):
            preview.manual(get_session(), 'a', 'member-a', rid, 1, 0)
            return bundle(), {}
        jobs.run_one(provider)
        s = get_session()
        assert s.get(OrganizeTask, tid).status == 'outdated'
        assert s.get(OrganizeRecord, rid).preview['body'] == SOURCE


def test_page_manual_preview_and_preserved_conflict_input(client, login):
    login('member-a'); rid = create(); path = '/f/a/organize/' + rid
    html = client.get(path).get_data(as_text=True)
    import re
    token = re.search(r'name="csrf_token" value="([^"]+)"', html)[1]
    data = {'csrf_token': token, 'revision': '1', 'preview_revision': '0', 'action': 'manual'}
    assert client.post(path+'/action', data=data).status_code == 302
    assert '核对预览' in client.get(path).get_data(as_text=True)
    data.update(action='preview', preview_revision='1', title='Edited', body='Saved')
    assert client.post(path+'/action', data=data).status_code == 302
    data['body'] = '<script>Old window</script>'
    response = client.post(path+'/action', data=data)
    assert response.status_code == 409
    assert '&lt;script&gt;Old window&lt;/script&gt;' in response.get_data(as_text=True)
    assert get_session().get(OrganizeRecord, rid).preview['body'] == 'Saved'
    login('owner-a')
    assert client.post(path+'/action', data=data).status_code == 400  # token tied to account
    assert client.get(path).status_code == 404
