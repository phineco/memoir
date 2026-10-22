def test_successful_save_clears_only_submitted_browser_copy(client, login):
    login()
    response = client.post('/f/a/write', data={'topic':'Recovered', 'content':'<p>local content</p>',
        'action':'draft', 'recovery_ids':'valid-recovery-123,bad!id'})
    assert response.status_code == 302
    with client.session_transaction() as sess:
        notice=sess['saved_write_recovery']
        assert notice == {'user':'owner-a','family':'a','story':'new','ids':['valid-recovery-123']}
        assert 'local content' not in str(notice)
    assert 'clearWriteRecoveries(' in client.get(response.location).get_data(as_text=True)
    assert 'clearWriteRecoveries(' not in client.get(response.location).get_data(as_text=True)


def test_invalid_save_retains_local_recovery(client, login):
    login()
    response=client.post('/f/a/write',data={'topic':'','content':'text','recovery_ids':'valid-recovery-123'})
    assert '标题和正文不能为空' in response.get_data(as_text=True)
    with client.session_transaction() as sess:
        assert 'saved_write_recovery' not in sess
