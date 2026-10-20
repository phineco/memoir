def test_management_keeps_admin_boundary(client, login):
    login('member-a')
    assert client.get('/f/a/more').status_code == 200
    assert client.get('/f/a/manage').status_code == 403
    assert client.get('/f/b/more').status_code == 404
    login('owner-a')
    assert client.get('/f/a/manage').status_code == 200
    assert '开通并加入本家庭' not in client.get('/f/a').get_data(as_text=True)
    response = client.post('/f/a/members/create-account', data={})
    assert response.location.endswith('/f/a/manage')
    assert '请填写家人姓名' in client.get(response.location).get_data(as_text=True)
