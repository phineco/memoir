from models import ShareSnapshot,get_session


def test_shares_use_canonical_origin_behind_internal_proxy(client):
    base='http://127.0.0.1:443'
    with client.session_transaction(base_url=base) as sess:sess['user_id']='owner-a'
    client.post('/f/a/shares/new',base_url=base)
    sid=get_session().query(ShareSnapshot).one().id
    client.post(f'/f/a/shares/{sid}/publish',data={'password':'local-test'},base_url=base)
    html=client.get('/f/a/shares',base_url=base,headers={'X-Forwarded-Host':'untrusted.invalid'}).get_data(as_text=True)
    assert 'https://family.scyllatech.cn/s/' in html
    assert 'http://127.0.0.1:443/s/' not in html and 'untrusted.invalid' not in html
    assert '复制分享链接' in html and '每篇最多 120 字' in html


def test_preview_snapshot_boundary_and_unpublish(client,login):
    login();client.post('/f/a/shares/new');snap=get_session().query(ShareSnapshot).one();sid=snap.id
    assert snap.status=='draft'
    assert [row['title'] for row in snap.content_json['stories']]==['public-a']
    preview=client.get(f'/f/a/shares/{sid}').get_data(as_text=True)
    assert '家庭导航' in preview and '非完整文章或电子书' in preview
    client.post(f'/f/a/shares/{sid}/publish',data={'password':'local-test'})
    token=get_session().query(ShareSnapshot).one().token
    client.get('/logout');assert '访问密码' in client.get('/s/'+token).get_data(as_text=True)
    assert 'public-a' in client.post('/s/'+token,data={'password':'local-test'}).get_data(as_text=True)
    login();client.post(f'/f/a/shares/{sid}/unpublish')
    client.get('/logout');assert client.get('/s/'+token).status_code==404
