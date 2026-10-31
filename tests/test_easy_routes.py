import re

import interviewing
import organizing
from models import FamilyMember,get_session


def test_easy_disabled_and_login_return(client,app):
    assert client.get('/easy').status_code==404
    app.config['EASY_ENABLED']=True
    response=client.get('/easy')
    assert response.status_code==302 and '/login?next=/easy' in response.location


def test_valid_family_resolution_and_account_switch(client,login,app):
    app.config['EASY_ENABLED']=True
    s=get_session();s.add(FamilyMember(id='member-both',family_id='b',user_id='member-a',role='member'));s.commit()
    login('member-a')
    assert '先选择一个家庭' in client.get('/easy').get_data(as_text=True)
    assert 'Alpha Family' in client.get('/easy?family_id=a').get_data(as_text=True)
    s.get(FamilyMember,'member').del_flag=1;s.commit()
    response=client.get('/easy')
    assert 'Beta Secret Family' in response.get_data(as_text=True) and 'Alpha Family' not in response.get_data(as_text=True)
    assert client.get('/easy?family_id=a').status_code==404
    login('owner-a')
    assert 'Alpha Family' in client.get('/easy').get_data(as_text=True)


def test_continue_private_interview_with_same_services_and_navigation(client,login,app):
    app.config['EASY_ENABLED']=True;s=get_session()
    row=interviewing.start(s,'a','member-a',{},'easy-session');sid=row.id
    organizing.create(s,'a','member-a',{'content':'仅自己的原稿','topic':'本人私有题目'})
    login('member-a')
    home=client.get('/easy').get_data(as_text=True)
    assert '继续上次讲述' in home and '/easy/f/a/interview/'+sid in home
    path='/easy/f/a/interview/'+sid
    html=client.get(path).get_data(as_text=True)
    assert 'easy-body' in html and 'site-menu-toggle' not in html
    csrf=re.search(r'name="csrf_token" value="([^"]+)"',html)[1]
    response=client.post(path+'/action',data={'csrf_token':csrf,'revision':1,'action':'pause'})
    assert response.status_code==302 and response.location==path
    assert interviewing.owned(s,'a','member-a',sid).state=='paused'
    assert '本人私有题目' in client.get('/easy/records').get_data(as_text=True)
    login('owner-a')
    assert client.get(path).status_code==404
    assert '本人私有题目' not in client.get('/easy/records').get_data(as_text=True)


def test_easy_reading_reuses_story_visibility_and_excludes_drafts(client,login,app):
    app.config['EASY_ENABLED']=True;login('member-a')
    listing=client.get('/easy/listen').get_data(as_text=True)
    assert 'public-a' in listing and 'specific-a' in listing
    assert 'private-a' not in listing and 'draft-a' not in listing and 'public-b' not in listing
    assert client.get('/easy/f/a/story/private-a').status_code==404
    assert client.get('/easy/f/a/story/specific-a').status_code==200
    assert client.get('/easy/f/b/story/public-b').status_code==404
    login('owner-a')
    assert client.get('/easy/f/a/story/private-a').status_code==200
    assert client.get('/easy/f/a/story/draft-a').status_code==404
    for path in ['/easy/settings','/easy/help','/easy/photos','/easy/families']:
        response=client.get(path)
        assert response.status_code==200 and 'no-store' in response.headers['Cache-Control']
    assert '当前版本' not in client.get('/easy').get_data(as_text=True)
    assert '版本：' in client.get('/easy/help').get_data(as_text=True)
