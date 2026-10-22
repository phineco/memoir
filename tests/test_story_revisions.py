from models import Draft,Interview,StoryCorrection,VerificationItem,get_session


def test_author_revises_published_with_history_and_stale_conflict(client,login):
    login();assert client.get('/f/a/story/public-a/edit').status_code==200
    form={'topic':'Revised','content':'<p>Corrected</p>','revision_reason':'Family checked','base_version':'1','action':'publish'}
    assert client.post('/f/a/story/public-a/edit',data=form).status_code==302
    versions=get_session().query(Draft).filter_by(interview_id='public-a').order_by(Draft.version).all()
    assert len(versions)==2 and versions[0].content=='content-public-a' and not versions[0].is_current
    assert versions[1].remarks=='Family checked'
    assert client.post('/f/a/story/public-a/edit',data=form).status_code==409
    assert client.get('/f/a/story/public-a/history').status_code==200
    login('member-a');assert client.get('/f/a/story/public-a/history').status_code==404
    assert client.get('/f/a/story/public-a/edit').status_code==404


def test_correction_only_accepted_with_successful_revision(client,login):
    login('member-a')
    assert client.post('/f/a/story/public-a/corrections',data={'proposal':'Corrected date','evidence':'Photo note','verification_id':'v-public-a'}).status_code==302
    c=get_session().query(StoryCorrection).one();cid=c.id
    assert client.post(f'/f/a/story/public-a/corrections/{cid}/review',data={'action':'accept'}).status_code==404
    login()
    assert client.post(f'/f/a/story/public-a/corrections/{cid}/review',data={'action':'accept'}).status_code==302
    assert get_session().query(StoryCorrection).one().status=='pending'
    data={'topic':'Corrected','content':'<p>Corrected date</p>','revision_reason':'Checked photo','base_version':'1','correction_id':cid}
    assert client.post('/f/a/story/public-a/edit',data=data).status_code==302
    assert get_session().query(StoryCorrection).one().status=='accepted'
    assert get_session().query(VerificationItem).filter_by(id='v-public-a').one().status=='resolved'


def test_private_and_cross_story_corrections_protected(client,login):
    login('member-a')
    assert client.post('/f/a/story/private-a/corrections',data={'proposal':'secret'}).status_code==404
    assert client.post('/f/b/story/public-b/corrections',data={'proposal':'secret'}).status_code==404
    assert client.post('/f/a/story/public-a/corrections',data={'proposal':'test','verification_id':'v-private-a'}).status_code==400


def test_administrator_only_curates_authorless_public_imports(client,login):
    s=get_session();s.query(Interview).filter_by(id='public-a').one().author_id=None;s.commit()
    login();assert client.get('/f/a/story/public-a/edit').status_code==200
    s.query(Interview).filter_by(id='private-a').one().author_id='member-a';s.commit()
    assert client.get('/f/a/story/private-a/edit').status_code==404
