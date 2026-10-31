import re

from models import UserDisplayPreference,get_session

VALUES={'theme':'paper','font':'serif','size':'26','mode':'simple','entry':'standard'}


def token(client):
    html=client.get('/display').get_data(as_text=True)
    return re.search(r'data-csrf="([^"]+)"',html)[1]


def save(client,values=VALUES,revision=0,user='member-a'):
    return client.post('/account/display-preferences',json={'values':values,'base_revision':revision,'expected_user_id':user},headers={'X-CSRF-Token':token(client)})


def test_opt_in_account_defaults_idempotency_and_stale_version(client,login):
    login('member-a');s=get_session()
    assert client.get('/account/display-preferences').json['values'] is None
    assert not s.query(UserDisplayPreference).count()
    first=save(client);assert first.status_code==200 and first.json['revision']==1
    assert save(client).json['revision']==1
    changed=dict(VALUES,size='22')
    assert save(client,changed,revision=0).status_code==409
    assert s.query(UserDisplayPreference).one().preferences['size']=='26'
    assert save(client,changed,revision=1).json['revision']==2
    assert 'no-store' in client.get('/account/display-preferences').headers['Cache-Control']


def test_account_switch_cannot_save_or_expose_other_defaults(client,login):
    login('member-a');assert save(client).status_code==200
    login('owner-a')
    assert client.get('/account/display-preferences').json['values'] is None
    assert save(client,user='member-a').status_code==409
    assert get_session().query(UserDisplayPreference).count()==1
    assert save(client,dict(VALUES,theme='contrast'),user='owner-a').status_code==200
    login('member-a');assert client.get('/account/display-preferences').json['values']['theme']=='paper'


def test_validation_csrf_and_disabled_sync(client,login,app):
    assert client.get('/account/display-preferences').status_code==401
    login('member-a')
    assert client.post('/account/display-preferences',json={'values':VALUES}).status_code==400
    assert save(client,dict(VALUES,size='999')).status_code==400
    assert save(client,dict(VALUES,unexpected='value')).status_code==400
    app.config['DISPLAY_ACCOUNT_SYNC_ENABLED']=False
    assert client.get('/account/display-preferences').status_code==404
    assert client.get('/display').status_code==200
