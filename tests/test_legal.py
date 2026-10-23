import datetime
import sqlite3

import pytest
from werkzeug.security import check_password_hash

from legal import PRIVACY_VERSION, TERMS_VERSION
from migrate import run_migrations
from models import FamilyMember, Invite, LegalAcceptance, SmsCode, User, get_session
from tests.test_migrations import old_database


def agreement_data():
    return {'legal_accepted':'yes', 'terms_version':TERMS_VERSION, 'privacy_version':PRIVACY_VERSION}


def registration_data():
    return dict(agreement_data(),phone='13800001234',password='test-password',nickname='Test Relative',code='123456')


def add_sms_and_invite():
    s=get_session()
    s.add(SmsCode(id='sms-test',phone='13800001234',purpose='register',code='123456',used=0,remarks='sms:v1:development',
                  expire_at=datetime.datetime.now()+datetime.timedelta(minutes=5)))
    s.add(Invite(id='invite-test',family_id='a',code='legal-test-invite',used_count=0,max_uses=2,
                 expire_at=datetime.datetime.now()+datetime.timedelta(days=1)))
    s.commit()


@pytest.mark.parametrize('path',['/terms','/privacy'])
def test_legal_documents_are_public_and_keep_valid_family_navigation(client,login,path):
    html=client.get(path).get_data(as_text=True)
    assert '安徽锡拉科技有限公司' in html
    assert '打印 / 保存 PDF' in html
    assert ('协议目录' in html or '隐私政策目录' in html)
    assert 'href="/logout"' not in html
    login()
    html=client.get(path+'?family_id=a').get_data(as_text=True)
    for label in ['故事','家人','记录','更多']:
        assert label in html
    assert client.get(path+'?family_id=b').status_code==404


def test_public_contact_is_configured_and_escaped(client,app):
    assert 'mailto:info@scyllatech.cn' in client.get('/privacy').get_data(as_text=True)
    app.config['PRIVACY_CONTACT_EMAIL']=''
    assert '尚未配置隐私联系邮箱' in client.get('/privacy').get_data(as_text=True)
    app.config['PRIVACY_CONTACT_EMAIL']='privacy@example.test'
    html=client.get('/privacy').get_data(as_text=True)
    assert 'mailto:privacy@example.test' in html and '尚未配置' not in html
    app.config['PRIVACY_CONTACT_EMAIL']='privacy@example.test"><script>bad()</script>'
    assert '<script>bad()</script>' not in client.get('/privacy').get_data(as_text=True)


@pytest.mark.parametrize('changes',[{'legal_accepted':''},{'legal_accepted':'no'},
                                    {'terms_version':'older'},{'privacy_version':'older'}])
def test_registration_requires_current_explicit_acknowledgement_before_any_write(client,changes):
    add_sms_and_invite()
    data=dict(registration_data(),invite_code='legal-test-invite');data.update(changes)
    count=get_session().query(User).count()
    response=client.post('/register',data=data)
    assert response.status_code==400
    assert '请阅读并同意当前版本' in response.get_data(as_text=True)
    assert get_session().query(User).count()==count
    assert get_session().query(LegalAcceptance).count()==0
    assert get_session().query(SmsCode).one().used==0
    assert get_session().query(Invite).one().used_count==0


def test_invited_registration_records_real_acceptance_and_joins_once(client):
    add_sms_and_invite()
    start=datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    response=client.post('/register?invite=legal-test-invite',data=registration_data())
    assert response.location.endswith('/f/a')
    s=get_session();user=s.query(User).filter_by(phone='13800001234').one()
    record=s.query(LegalAcceptance).one()
    assert (record.user_id,record.terms_version,record.privacy_version)==(user.id,TERMS_VERSION,PRIVACY_VERSION)
    assert record.accepted_at >= start
    assert check_password_hash(user.password_hash,'test-password')
    assert s.query(FamilyMember).filter_by(user_id=user.id,family_id='a',del_flag=0).count()==1
    assert s.query(Invite).one().used_count==1
    assert s.query(SmsCode).one().used==1


def test_invalid_registration_does_not_create_acceptance_or_echo_password(client):
    data=registration_data();data['phone']='bad'
    html=client.post('/register',data=data).get_data(as_text=True)
    assert '手机号应为 11 位数字' in html
    assert 'value="test-password"' not in html
    assert get_session().query(LegalAcceptance).count()==0


def test_registration_sms_requires_acknowledgement_before_external_send(client,monkeypatch):
    import sms
    sent=[]
    monkeypatch.setattr(sms,'send_code',lambda phone,purpose:sent.append((phone,purpose)) or {'dev_mode':False})
    payload={'phone':'13800001234','purpose':'register'}
    assert client.post('/api/sms-code',json=payload).status_code==400
    assert sent==[]
    assert client.post('/api/sms-code',json=dict(payload,**agreement_data())).json['ok']
    assert sent==[('13800001234','register')]


def test_provisioning_or_existing_login_never_infers_acceptance(client,login):
    login()
    response=client.post('/f/a/members/create-account',data={
        'real_name':'Relative','phone':'13800001234','password':'test-password'})
    assert response.status_code==302
    assert get_session().query(LegalAcceptance).count()==0
    client.get('/logout')
    assert client.post('/login',data={'phone':'13800001234','password':'test-password'}).status_code==302
    assert get_session().query(LegalAcceptance).count()==0


def test_new_legal_migration_is_additive_and_keeps_existing_accounts_unconfirmed(tmp_path):
    path=old_database(tmp_path)
    run_migrations('sqlite:///'+str(path))
    run_migrations('sqlite:///'+str(path))
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT nickname FROM users').fetchone()[0]=='preserved'
        assert db.execute('SELECT COUNT(*) FROM legal_acceptances').fetchone()[0]==0
        db.execute("INSERT INTO legal_acceptances(id,user_id,terms_version,privacy_version,accepted_at) VALUES ('l','old','v1','v1','2026-10-21 00:00:00')")
    run_migrations('sqlite:///'+str(path))
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT COUNT(*) FROM legal_acceptances').fetchone()[0]==1
