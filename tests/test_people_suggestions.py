import pytest
from werkzeug.exceptions import HTTPException

import organizing
import organize_drafts
import people_suggestions as people
from models import NewPerson,Person,InterviewPerson,Draft,get_session
from test_organize_provider import SOURCE,bundle


def source(public=True):
    s=get_session();record=organizing.create(s,'a','member-a',{'content':SOURCE})
    record.preview=bundle();record.preview_source_revision=1;record.preview_revision=1;s.commit()
    story=organize_drafts.confirm(s,'a','member-a',record.id,1,1,'confirm-source')
    if public:story.publish_status='published';story.visibility='public';s.commit()
    return record.id,story.id


def share(rid):
    people.share(get_session(),'a','member-a',rid,1,1,1,['0'])
    return get_session().query(NewPerson).filter_by(source_record_id=rid).one().id


def test_private_sources_do_not_enter_family_queue_and_admin_cannot_read_raw(app):
    s=get_session();rid,sid=source(False)
    with pytest.raises(HTTPException):share(rid)
    s.rollback();assert not s.query(NewPerson).count()
    with pytest.raises(HTTPException):organizing.owned(s,'a','owner-a',rid)


def test_explicit_public_submission_idempotent_and_member_cannot_create_tree(app,client,login):
    s=get_session();rid,sid=source();cid=share(rid);assert share(rid)==cid
    assert s.query(NewPerson).count()==1 and s.query(Person).count()==2
    with pytest.raises(HTTPException) as e:people.review(s,'a','member-a',cid,1,'create',name='妈妈')
    assert e.value.code==403;s.rollback()
    with pytest.raises(HTTPException):people.review(s,'a','owner-a',cid,1,'link',person_id='pb')
    s.rollback();assert people.review(s,'a','owner-a',cid,1,'link',person_id='pa')=='pa'
    assert people.review(s,'a','owner-a',cid,1,'create',name='不应新增')=='pa'
    assert s.query(Person).count()==2 and not s.query(InterviewPerson).filter_by(interview_id=sid).count()


def test_same_name_requires_manual_confirmation_and_no_automatic_relationship(app):
    s=get_session();rid,sid=source();cid=share(rid)
    with pytest.raises(HTTPException):people.review(s,'a','owner-a',cid,1,'create',name='Alpha Person')
    s.rollback()
    pid=people.review(s,'a','owner-a',cid,1,'create',name='Alpha Person',duplicate=True)
    person=s.get(Person,pid)
    assert pid!='pa' and person.parent_id=='0' and person.life_state=='unknown' and person.status=='pending'


def test_changed_public_evidence_disappears_from_queue_and_ai(app,client,login):
    s=get_session();rid,sid=source();cid=share(rid)
    draft=s.query(Draft).filter_by(interview_id=sid,is_current=True).one();draft.content='<p>只保留一段无名的回忆。</p>';draft.version=2;s.commit()
    assert not people.readable(s,s.get(NewPerson,cid))
    login('owner-a');assert '妈妈' not in client.get('/f/a/people/suggestions').get_data(as_text=True)
    from ai import family_knowledge
    assert '妈妈' not in family_knowledge('a')
    with pytest.raises(HTTPException):people.review(s,'a','owner-a',cid,1,'create',name='妈妈')
    assert s.query(Person).count()==2
