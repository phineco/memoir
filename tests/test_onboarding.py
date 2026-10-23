import re

from models import Family,FamilyMember,FamilyVisit,Interview,get_session


def csrf(client,path='/f/a'):
    body=client.get(path).get_data(as_text=True)
    return re.search(r'name="csrf_token" value="([^"]+)"',body).group(1)


def test_member_can_skip_guide_and_reopen_it_without_affecting_other_families(client,login):
    login('member-a');s=get_session()
    s.add_all([Family(id='c',name='Empty',owner_user_id='owner-b'),FamilyMember(id='mc',family_id='c',user_id='member-a',role='member')]);s.commit()
    token=csrf(client)
    assert client.post('/f/a/onboarding',data={'action':'hide'}).status_code==400
    assert client.post('/f/a/onboarding',data={'action':'hide','csrf_token':token}).status_code==302
    assert 'id="onboarding-guide"' not in client.get('/f/a').get_data(as_text=True)
    other=client.get('/f/c').get_data(as_text=True)
    assert 'id="onboarding-guide"' in other and '不必等待认领' in other
    assert '/f/c/tree/add' not in other
    assert client.post('/f/a/onboarding',data={'action':'show','csrf_token':token}).status_code==302
    assert 'id="onboarding-guide"' in client.get('/f/a').get_data(as_text=True)


def test_first_visit_does_not_change_and_read_progress_requires_permission(client,login):
    login('member-a');client.get('/f/a')
    visit=get_session().query(FamilyVisit).one();first=visit.first_seen_at
    assert visit.first_read_at is None
    assert client.get('/f/a/story/private-a').status_code==404
    assert get_session().query(FamilyVisit).one().first_read_at is None
    client.get('/f/a/story/public-a');client.get('/f/a')
    visit=get_session().query(FamilyVisit).one()
    assert visit.first_seen_at==first and visit.first_read_at is not None
    login('outsider');assert client.get('/f/a').status_code==404
    assert get_session().query(FamilyVisit).count()==1


def test_member_can_save_without_person_and_first_save_is_recorded_atomically(client,login):
    login('member-a')
    response=client.post('/f/a/write',data={'topic':'No claim required','content':'<p>A memory.</p>','action':'draft'})
    assert response.status_code==302
    visit=get_session().query(FamilyVisit).one()
    assert visit.cohort_eligible and visit.first_saved_at is not None
    assert visit.first_published_at is None
    story=get_session().query(Interview).filter_by(author_id='member-a').one()
    assert story.person_id is None


def test_existing_authors_are_not_invented_as_new_conversion_cohort(client,login):
    login();client.get('/f/a')
    visit=get_session().query(FamilyVisit).one()
    assert not visit.cohort_eligible and visit.first_saved_at is None
