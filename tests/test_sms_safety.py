import datetime
import json

import pytest

from config import Config
from legal import TERMS_VERSION, PRIVACY_VERSION
from models import SmsCode, User, get_session
import sms


@pytest.mark.parametrize('purpose', ['register', 'login', 'reset'])
@pytest.mark.parametrize('environment,development', [('cloud',False), ('cloud',True), ('local',False)])
def test_missing_sms_configuration_never_returns_or_accepts_code(client, monkeypatch, purpose, environment, development):
    monkeypatch.setattr(Config, 'APP_ENV', environment)
    monkeypatch.setattr(Config, 'SMS_DEVELOPMENT_MODE', development)
    s=get_session()
    s.query(User).filter_by(id='owner-a').update({User.phone:'13800001234'})
    s.commit()
    payload=dict(phone='13800005678' if purpose=='register' else '13800001234', purpose=purpose,
                 legal_accepted='yes',terms_version=TERMS_VERSION,privacy_version=PRIVACY_VERSION)
    response=client.post('/api/sms-code',json=payload)
    assert response.status_code==400 and not response.json['ok']
    assert 'dev_code' not in response.json and 'code' not in response.json
    assert s.query(SmsCode).count()==0
    with pytest.raises(sms.SMSError,match='暂不可用'):
        sms.verify_code(payload['phone'],'123456',purpose)


def test_explicit_development_codes_are_not_logged_and_are_one_use(app, caplog):
    result=sms.send_code('13800001234','login')
    assert result['dev_mode']
    assert result['code'] not in caplog.text
    with pytest.raises(sms.SMSError):sms.verify_code('13800001234',result['code'],'reset')
    sms.verify_code('13800001234',result['code'],'login')
    with pytest.raises(sms.SMSError):sms.verify_code('13800001234',result['code'],'login')


def test_development_or_legacy_codes_do_not_work_after_provider_is_enabled(app, monkeypatch):
    result=sms.send_code('13800001234','login')
    monkeypatch.setattr(Config,'SMS_ENABLED',True)
    monkeypatch.setattr(Config,'APP_ENV','cloud')
    with pytest.raises(sms.SMSError):sms.verify_code('13800001234',result['code'],'login')
    s=get_session()
    s.add(SmsCode(id='legacy',phone='13800005678',purpose='login',code='123456',used=0,
                  expire_at=datetime.datetime.now()+datetime.timedelta(minutes=10)))
    s.commit()
    with pytest.raises(sms.SMSError):sms.verify_code('13800005678','123456','login')


def test_provider_success_never_exposes_code_and_failure_does_not_activate_code(app, monkeypatch, caplog):
    monkeypatch.setattr(Config,'SMS_ENABLED',True)
    monkeypatch.setattr(Config,'APP_ENV','cloud')
    sent=[]
    monkeypatch.setattr(sms,'_send_sms_api',lambda phone,payload:sent.append(json.loads(payload)['code']))
    assert sms.send_code('13800001234','login')=={'dev_mode':False}
    assert len(sent)==1 and sent[0] not in caplog.text
    sms.verify_code('13800001234',sent[0],'login')
    def fail(*args):raise sms.SMSError('synthetic provider failure')
    monkeypatch.setattr(sms,'_send_sms_api',fail)
    with pytest.raises(sms.SMSError):sms.send_code('13800005678','login')
    assert get_session().query(SmsCode).filter_by(phone='13800005678').count()==0


def test_expired_code_is_rejected(app):
    result=sms.send_code('13800001234','register')
    s=get_session();s.query(SmsCode).one().expire_at=datetime.datetime.now()-datetime.timedelta(seconds=1);s.commit()
    with pytest.raises(sms.SMSError,match='过期'):sms.verify_code('13800001234',result['code'],'register')
