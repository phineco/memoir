import datetime
import json
import re

import pytest
from werkzeug.exceptions import HTTPException

import organizing
import organize_drafts
import plan_suggestions as plans
from models import WritingPlan,Person,Interview,PlanProgressSuggestion,get_session
from test_organize_provider import SOURCE,bundle


def setup():
    s=get_session();record=organizing.create(s,'a','member-a',{'content':SOURCE,'subject_id':'pa'})
    record.preview=bundle();record.preview_revision=1;record.preview_source_revision=1;s.commit()
    story=organize_drafts.confirm(s,'a','member-a',record.id,1,1,'confirm-source')
    plan=WritingPlan(id='plan-a',family_id='a',title='今年的采访',status='active',items=json.dumps([
        {'person_id':'pa','person_name':'Alpha Person','status':'pending','note':'核对童年'},
        {'person_id':'other','person_name':'另一个人','status':'pending'}]))
    s.add(plan);s.commit();return record.id,story.id


def publish(sid):
    story=get_session().get(Interview,sid);story.publish_status='published';story.visibility='public';story.published_at=datetime.datetime(2026,10,31,12);get_session().commit()


def propose(rid):
    s=get_session();record=s.get(__import__('models').OrganizeRecord,rid);option=plans.options(s,record)[0]
    return plans.propose(s,'a','member-a',rid,option['plan_id'],option['index'],option['stamp'],option['version']).id


def test_private_story_does_not_affect_shared_plan_and_admin_confirms_only_doing(app):
    s=get_session();rid,sid=setup();plan=s.get(WritingPlan,'plan-a')
    assert not plans.options(s,s.get(__import__('models').OrganizeRecord,rid))
    with pytest.raises(HTTPException):plans.propose(s,'a','member-a',rid,plan.id,0,plans.stamp(plan),1)
    s.rollback();assert plans.items(plan)[0]['status']=='pending'
    publish(sid);suggestion=propose(rid);assert propose(rid)==suggestion
    assert s.query(PlanProgressSuggestion).count()==1 and plans.items(plan)[0]['status']=='pending'
    with pytest.raises(HTTPException) as e:plans.review(s,'a','member-a',suggestion,'apply')
    assert e.value.code==403;s.rollback()
    assert plans.review(s,'a','owner-a',suggestion,'apply').status=='applied'
    assert plans.review(s,'a','owner-a',suggestion,'apply').status=='applied'
    assert [item['status'] for item in plans.items(plan)]==['doing','pending']
    assert s.get(Person,'pa').status is None


def test_changed_plan_or_restricted_story_rejects_old_suggestion(app):
    s=get_session();rid,sid=setup();publish(sid);suggestion=propose(rid);plan=s.get(WritingPlan,'plan-a')
    values=plans.items(plan);values[0]['note']='新的采访重点';plan.items=json.dumps(values);s.commit()
    with pytest.raises(HTTPException) as e:plans.review(s,'a','owner-a',suggestion,'apply')
    assert e.value.code==409;s.rollback()
    assert plans.items(plan)[0]['status']=='pending'
    s.get(Interview,sid).visibility='private';s.commit()
    assert not plans.pending(s,'a')
    with pytest.raises(HTTPException):plans.review(s,'a','owner-a',suggestion,'apply')


def test_stale_manual_plan_form_does_not_undo_confirmed_progress(app,client,login):
    s=get_session();rid,sid=setup();publish(sid);suggestion=propose(rid)
    login('owner-a');html=client.get('/f/a/plans/plan-a/edit').get_data(as_text=True)
    fields={name:re.search(r'name="'+name+r'" value="([^"]+)"',html)[1] for name in ('csrf_token','base_stamp')}
    plans.review(s,'a','owner-a',suggestion,'apply')
    response=client.post('/f/a/plans/plan-a/update',data=dict(fields,title='旧页面',person_id='pa',item_status='pending'))
    assert response.status_code==409 and plans.items(s.get(WritingPlan,'plan-a'))[0]['status']=='doing'


def test_weekly_uses_first_publication_and_keeps_draft_verification_private(app):
    from views import _weekly_data
    s=get_session();rid,sid=setup();story=s.get(Interview,sid);story.create_date=datetime.datetime(2026,10,10);s.commit()
    assert sid not in {row.id for row in _weekly_data('a',44,year=2026)['interviews']}
    publish(sid)
    data=_weekly_data('a',44,year=2026)
    assert sid in {row.id for row in data['interviews']}
    assert any(item.interview_id==sid and item.status=='pending' for item in data['verifs'])
    assert sid not in {row.id for row in _weekly_data('a',41,year=2026)['interviews']}
    story.visibility='private';s.commit()
    data=_weekly_data('a',44,year=2026)
    assert sid not in {row.id for row in data['interviews']} and not any(item.interview_id==sid for item in data['verifs'])
