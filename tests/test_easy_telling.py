import re

import interviewing
from models import get_session


def csrf(html):
    return re.search(r'name="csrf_token" value="([^"]+)"', html)[1]


def test_easy_start_moves_config_to_optional_fields_and_defaults_to_free(app, client, login, monkeypatch):
    import interview_questions
    monkeypatch.setattr(interview_questions, 'enabled', lambda: True)
    app.config['EASY_ENABLED'] = True
    login()
    html = client.get('/easy/f/a/interview/new').get_data(as_text=True)
    assert '<option value="free" selected>' in html
    assert html.index('开始这一段') < html.index('话题与讲述身份（可选）')
    assert 'type="checkbox"' not in html
    assert 'name="ai_consent"' in html
    full = client.get('/f/a/interview/new').get_data(as_text=True)
    assert 'type="checkbox" name="ai_consent"' in full


def test_easy_recording_choices_are_explicit_and_text_is_secondary(app, client, login, monkeypatch):
    import interview_asr
    monkeypatch.setattr(interview_asr, 'enabled', lambda: True)
    app.config['EASY_ENABLED'] = True
    row = interviewing.start(get_session(), 'a', 'owner-a', {'recording_mode': 'self'}, 'easy-simple-1')
    sid = row.id
    login()
    html = client.get('/easy/f/a/interview/' + sid).get_data(as_text=True)
    assert '<input id="recording-consent" type="checkbox" hidden>' in html
    assert '<input id="recording-asr-consent" type="checkbox" hidden>' in html
    assert 'data-record-choice="asr"' in html and 'data-record-choice="save"' in html
    assert 'data-record-choice="off"' in html and '听一下说明' in html
    assert '<details id="interview-text" >' in html
    assert '<details id="easy-interview-options">' in html
    assert 'id="record-phase"' in html and 'id="record-elapsed"' in html
    assert 'id="record-file-form"' in html


def test_easy_invalid_answer_reopens_text_and_retains_content(app, client, login):
    app.config['EASY_ENABLED'] = True
    row = interviewing.start(get_session(), 'a', 'owner-a', {}, 'easy-simple-2')
    sid = row.id
    login()
    route = '/easy/f/a/interview/' + sid
    html = client.get(route).get_data(as_text=True)
    nonce = re.search(r'name="nonce" value="([^"]+)"', html)[1]
    answer = '保留我的回答' * 800
    response = client.post(route + '/action', data={'csrf_token': csrf(html), 'revision': 1,
        'nonce': nonce, 'action': 'answer', 'answer': answer})
    assert response.status_code == 400
    result = response.get_data(as_text=True)
    assert '<details id="interview-text" open>' in result
    assert answer in result
    assert not interviewing.answers(get_session(), sid)


def test_easy_accompany_notice_keeps_speaker_consent_and_unavailable_asr_clear(app, client, login):
    app.config['EASY_ENABLED'] = True
    row = interviewing.start(get_session(), 'a', 'owner-a', {'recording_mode': 'accompany'}, 'easy-simple-3')
    sid = row.id
    login()
    html = client.get('/easy/f/a/interview/' + sid).get_data(as_text=True)
    assert '请先向讲述者说明并取得同意' in html
    assert '转文字暂未开通；录音仍可保存和回听' in html
    assert 'data-record-choice="asr"' not in html
