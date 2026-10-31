import io
from PIL import Image


def test_public_manifest_scope_icons_and_no_private_metadata(app,client):
    app.config.update(EASY_ENABLED=True,EASY_PWA_ENABLED=True)
    data=client.get('/easy/manifest.webmanifest').json
    assert data['id']==data['start_url']==data['scope']=='/easy'
    assert 'family_id' not in str(data) and data['display']=='standalone'
    for icon in data['icons']:
        response=client.get(icon['src'])
        image=Image.open(io.BytesIO(response.data));assert image.size in [(192,192),(512,512)]
    response=client.get('/easy/sw.js')
    assert response.status_code==200 and response.headers['Service-Worker-Allowed']=='/easy'
    script=response.get_data(as_text=True)
    assert '__ASSETS__' not in script and '__VERSION__' not in script
    assert 'network-only' in script and 'skipWaiting' in script
    assert 'ui-user' not in script and 'family_id=' not in script
    app.config['EASY_PWA_ENABLED']=False
    assert client.get('/easy/manifest.webmanifest').status_code==404
    assert client.get('/easy/sw.js').status_code==404


def test_installed_login_keeps_safe_task_return_and_blocks_foreign_urls(app,client):
    from werkzeug.security import generate_password_hash
    from models import get_session,User
    app.config.update(EASY_ENABLED=True,EASY_PWA_ENABLED=True)
    get_session().get(User,'member-a').password_hash=generate_password_hash('test-only-password');get_session().commit()
    response=client.get('/easy/records')
    assert '/easy/login?next=' in response.location
    page=client.get(response.location)
    assert page.status_code==200 and 'easy-body' in page.get_data(as_text=True)
    assert 'easy-nav' not in page.get_data(as_text=True)
    response=client.post('/easy/login?next=/easy/records',data={'phone':'member-a','password':'test-only-password'})
    assert response.status_code==302 and response.location=='/easy/records'
    assert client.post('/easy/login?next=https://outside.invalid/',data={'phone':'member-a','password':'test-only-password'}).status_code==400
