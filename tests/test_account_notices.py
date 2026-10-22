import json
import time
import account_notices
from models import User,get_session


def test_client_session_contains_reference_only_and_results_consumed(client,login,app,tmp_path):
    app.config['ACCOUNT_NOTICE_DIR']=str(tmp_path/'notices');login()
    password='local-test-password'
    response=client.post('/f/a/members/create-account',data={'real_name':'Temporary','phone':'13800007777','password':password})
    with client.session_transaction() as sess:
        token=sess['created_account'];assert isinstance(token,str) and len(token)==43
        assert password not in json.dumps(dict(sess))
    assert password not in response.headers.get('Location','')
    assert password in client.get(response.location).get_data(as_text=True)
    assert password not in client.get(response.location).get_data(as_text=True)
    assert list((tmp_path/'notices').glob('*.json'))==[]


def test_one_time_results_bound_to_actor_family_kind_and_ttl(app,tmp_path,monkeypatch):
    app.config['ACCOUNT_NOTICE_DIR']=str(tmp_path/'notices')
    with app.app_context():
        token=account_notices.store('owner-a','a','reset_notice',{'password':'test-only'})
        for who,family,kind in [('member-a','a','reset_notice'),('owner-a','b','reset_notice'),('owner-a','a','created_account')]:
            assert account_notices.take(token,who,family,kind) is None
        assert account_notices.take(token,'owner-a','a','reset_notice')=={'password':'test-only'}
        assert account_notices.take(token,'owner-a','a','reset_notice') is None
        token=account_notices.store('owner-a','a','reset_notice',{'password':'test-only'})
        monkeypatch.setattr(account_notices.time,'time',lambda:time.monotonic()+10**12)
        assert account_notices.take(token,'owner-a','a','reset_notice') is None


def test_legacy_plaintext_results_dropped_on_any_request(client,login):
    login()
    with client.session_transaction() as sess:sess['reset_notice']={'password':'legacy-only'}
    client.get('/f/a/stories')
    with client.session_transaction() as sess:assert 'reset_notice' not in sess


def test_expired_claim_from_interrupted_reader_is_cleaned(app,tmp_path):
    import os
    app.config['ACCOUNT_NOTICE_DIR']=str(tmp_path/'notices')
    with app.app_context():
        token=account_notices.store('owner-a','a','reset_notice',{'password':'temporary-only'})
        path=account_notices._path(token)
        claimed=path.with_name(path.name+'.'+'a'*16+'.claimed');path.rename(claimed)
        os.utime(claimed,(1,1));account_notices.cleanup()
        assert not claimed.exists()
