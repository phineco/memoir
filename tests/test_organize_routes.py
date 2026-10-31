import io
import re

from models import OrganizeRecord, get_session


def form(client):
    page = client.get('/f/a/organize/new').get_data(as_text=True)
    return {key: re.search(r'name="'+key+r'" value="([^"]+)"', page)[1] for key in ('csrf_token', 'nonce')}


def test_save_upload_resume_and_private_export(client, login):
    login('member-a')
    data = form(client)
    response = client.post('/f/a/organize/new', data=dict(data, content='小时候在河边长大。', topic='Childhood'))
    assert response.status_code == 302
    target = response.location.split('?')[0]
    assert client.post('/f/a/organize/new', data=dict(data, content='小时候在河边长大。', topic='Childhood')).location.split('?')[0] == target
    assert get_session().query(OrganizeRecord).count() == 1
    assert '小时候在河边长大。' in client.get(target).get_data(as_text=True)
    exported = client.get(target+'/source')
    assert exported.data.decode() == '小时候在河边长大。'
    assert 'no-store' in exported.headers['Cache-Control']
    assert 'Childhood' in client.get('/account/organize').get_data(as_text=True)
    login('owner-a')
    assert client.get(target).status_code == 404
    assert client.get(target+'/source').status_code == 404
    assert 'Childhood' not in client.get('/account/organize').get_data(as_text=True)


def test_upload_rules_and_csrf(client, login):
    login()
    assert client.post('/f/a/organize/new', data={'content': 'No token'}).status_code == 400
    data = form(client)
    response = client.post('/f/a/organize/new', data=dict(data, source=(io.BytesIO('原稿文件'.encode()), 'memory.md')))
    assert response.status_code == 302
    assert get_session().query(OrganizeRecord).one().content == '原稿文件'
    for name, raw in [('bad.pdf', b'%PDF'), ('bad.txt', b'\xff\xff')]:
        assert client.post('/f/a/organize/new', data=dict(form(client), source=(io.BytesIO(raw), name))).status_code == 400
    response = client.post('/f/a/organize/new', data=dict(form(client), content='Keep this', source=(io.BytesIO(b'File'), 'memory.txt')))
    assert response.status_code == 400 and 'Keep this' in response.get_data(as_text=True)


def test_stale_window_keeps_submitted_text_and_never_overwrites(client, login):
    login()
    data = form(client)
    response = client.post('/f/a/organize/new', data=dict(data, content='First'))
    target = response.location.split('?')[0]
    assert client.post(target, data=dict(data, revision='1', content='Second')).status_code == 302
    response = client.post(target, data=dict(data, revision='1', content='<script>Old copy</script>'))
    assert response.status_code == 409
    assert '&lt;script&gt;Old copy&lt;/script&gt;' in response.get_data(as_text=True)
    assert get_session().query(OrganizeRecord).one().content == 'Second'
