import datetime as dt
import re
import sqlite3

import pytest

import ai
import ai_turns
from models import AiTurn,FamilyVisit,Interview,MetricSample,StoryPublication,UsageEvent,VerificationItem,get_session
from product_metrics import build_report
from reporting import current_period,local_now,report_period
from migrate import run_migrations
from tests.test_migrations import old_database


def csrf(client,path='/account/privacy-requests'):
    body=client.get(path).get_data(as_text=True)
    # The metrics dashboard always has a protected sample form.
    match=re.search(r'name="csrf_token" value="([^"]+)"',body)
    if match:return match.group(1)
    match=re.search(r'name="csrf-token" content="([^"]+)"',body)
    return match.group(1)


def test_metrics_are_operator_only_and_no_samples_are_not_reported_as_zero(client,login,app):
    login();assert client.get('/operations/metrics').status_code==403
    app.config['OPERATIONS_USER_IDS']=('owner-a',)
    body=client.get('/operations/metrics').get_data(as_text=True)
    assert '暂无样本' in body and '浏览器样本记录未启用' in body
    assert 'content-private-a' not in body


def test_collection_requires_an_active_operator_and_retention_never_deletes_stories(app):
    from product_metrics import collection_enabled
    from tools.usage_retention import expire_samples
    now=local_now();s=get_session()
    with app.app_context():
        app.config.update(USAGE_METRICS_ENABLED=True,OPERATIONS_USER_IDS=('missing-user',))
        assert not collection_enabled()
        app.config['OPERATIONS_USER_IDS']=('owner-a',)
        assert collection_enabled()
    for identifier,age in [('old',91),('boundary',90),('recent',1)]:
        s.add(UsageEvent(id=identifier,family_id='a',user_id='owner-a',kind='retention',outcome='success',duration_ms=1,create_date=now-dt.timedelta(days=age)))
    s.commit();stories=s.query(Interview).count()
    assert expire_samples(s,now)==1 and s.query(UsageEvent).count()==3
    assert expire_samples(s,now,apply=True)==1
    assert {row.id for row in s.query(UsageEvent)}=={'boundary','recent'}
    assert s.query(Interview).count()==stories


def test_status_collection_is_minimal_scoped_idempotent_and_csrf_protected(client,login,app):
    app.config.update(USAGE_METRICS_ENABLED=True,OPERATIONS_USER_IDS=('owner-b',))
    login();token=csrf(client,'/f/a')
    event={'id':'unique-event-id','kind':'retention','outcome':'success','duration_ms':2}
    payload={'user_id':'owner-a','events':[event]}
    assert client.post('/f/a/usage',json=payload).status_code==400
    headers={'X-CSRF-Token':token}
    assert client.post('/f/a/usage',json=payload,headers=headers).json['accepted']==1
    assert client.post('/f/a/usage',json=payload,headers=headers).json['accepted']==0
    assert get_session().query(UsageEvent).count()==1
    assert client.post('/f/a/usage',json={**payload,'body':'NEVER_STORE'},headers=headers).status_code==400
    assert client.post('/f/b/usage',json=payload,headers=headers).status_code==404
    with client.session_transaction() as state:state['user_id']='member-a'
    assert client.post('/f/a/usage',json=payload,headers=headers).status_code==400


def test_first_save_conversion_requires_mature_observation_and_excludes_existing_authors(app):
    s=get_session();year,week=2026,40;_,_,start,_=report_period(week,year)
    s.add_all([FamilyVisit(id='one',family_id='a',user_id='owner-a',first_seen_at=start,first_saved_at=start+dt.timedelta(days=1),cohort_eligible=True),
               FamilyVisit(id='two',family_id='a',user_id='member-a',first_seen_at=start,cohort_eligible=True),
               FamilyVisit(id='old',family_id='b',user_id='owner-b',first_seen_at=start,first_saved_at=start,cohort_eligible=False)])
    s.commit();result=build_report(year,week)
    assert result['conversion']['mature']==2 and result['conversion']['saved_rate']==50.0


def test_weekly_omission_audits_independent_publication_evidence(app,monkeypatch):
    import views
    s=get_session();year,week=current_period();_,_,start,_=report_period(week,year)
    story=s.query(Interview).filter_by(id='public-a').one();story.published_at=start+dt.timedelta(hours=1);s.commit()
    assert s.query(StoryPublication).filter_by(id='public-a').one().published_at==story.published_at
    first=build_report(year,week);assert first['weekly']['checked']==1 and first['weekly']['missing']==0
    monkeypatch.setattr(views,'_weekly_data',lambda *args,**kwargs:{'interviews':[]})
    assert build_report(year,week)['weekly']['missing']==1


def test_verification_duration_uses_real_resolution_and_excludes_unknown_history(app,monkeypatch):
    import reporting
    from sqlalchemy import text
    s=get_session();year,week=2026,40;_,_,start,_=report_period(week,year)
    monkeypatch.setattr(reporting,'local_now',lambda:start+dt.timedelta(hours=6))
    first=s.query(VerificationItem).filter_by(id='v-public-a').one()
    legacy=s.query(VerificationItem).filter_by(id='v-private-a').one()
    first.create_date=legacy.create_date=start;first.status='resolved';s.commit()
    s.execute(text("UPDATE verification_items SET status='resolved',resolved_at=NULL WHERE id='v-private-a'"));s.commit()
    result=build_report(year,week)['verifications']
    assert result==dict(count=2,resolved=2,rate=100.0,timed=1,hours=6.0)
    first.correction='More detail';s.commit();assert first.resolved_at==start+dt.timedelta(hours=6)
    first.status='pending';s.commit();assert first.resolved_at is None
    assert build_report(year,week)['verifications']['rate']==50.0


def test_ai_retries_have_explicit_lineage_and_cannot_attach_to_another_user(app):
    with app.test_request_context():
        original,_=ai_turns.begin('a','owner-a','original-failure','same question')
        original.status='failed';get_session().commit();identifier=original.id
        retry,_=ai_turns.begin('a','owner-a','retry-success','same question',retry_of='original-failure')
        assert retry.logical_id==identifier
        retry.status='succeeded';get_session().commit()
        year,week=current_period();report=build_report(year,week)
        assert report['ai']['failed']==1 and report['ai']['recovered']==1
        with pytest.raises(ai_turns.TurnConflict):ai_turns.begin('a','member-a','unrelated-retry','same question',retry_of='original-failure')


def test_manual_samples_require_evidence_and_can_be_voided_without_deleting_audit(app,client,login):
    app.config['OPERATIONS_USER_IDS']=('owner-a',);login()
    body=client.get('/operations/metrics').get_data(as_text=True)
    token=re.search(r'name="csrf_token" value="([^"]+)"',body).group(1)
    nonce=re.search(r'name="nonce" value="([^"]+)"',body).group(1)
    data=dict(csrf_token=token,nonce=nonce,kind='elder_task',task='large_text',device='iPhone / Safari test',evidence_ref='qa-test-001',sample_count='5',success_count='4',assisted_success='1')
    assert client.post('/operations/metrics',data=data).status_code==302
    assert client.post('/operations/metrics',data=data).status_code==302
    row=get_session().query(MetricSample).one();identifier=row.id
    year,week=current_period();result=build_report(year,week)
    assert result['manual']['elder_task']['rate']==80 and result['manual']['elder_task']['independent_rate']==60
    assert client.post('/operations/metrics',data=dict(csrf_token=token,action='void',sample_id=identifier,reason='输入错误')).status_code==302
    row=get_session().query(MetricSample).one();assert row.del_flag==1 and row.void_reason=='输入错误'
    assert build_report(year,week)['manual']['elder_task']['count']==0


def test_known_publication_backfill_preserves_fact_time_and_records_real_migration_time(tmp_path):
    path=old_database(tmp_path)
    with sqlite3.connect(path) as conn:
        conn.execute('ALTER TABLE interviews ADD COLUMN published_at DATETIME')
        conn.execute("INSERT INTO interviews (id,family_id,author_id,published_at) VALUES ('known','family','owner','2020-01-02 03:04:05')")
        conn.execute("INSERT INTO interviews (id,family_id,author_id) VALUES ('unknown','family','owner')")
    run_migrations('sqlite:///'+str(path));run_migrations('sqlite:///'+str(path))
    with sqlite3.connect(path) as conn:
        row=conn.execute("SELECT published_at,create_date,remarks FROM story_publications WHERE id='known'").fetchone()
        assert row[0]=='2020-01-02 03:04:05' and row[1]>'2026-01-01'
        assert row[2]=='known-time-backfill'
        assert conn.execute("SELECT COUNT(*) FROM story_publications WHERE id='unknown'").fetchone()[0]==0
