import sqlite3
import pytest
from models import Person, get_session
from person_dates import DATE_FIELDS, form_values
from migrate import run_migrations


def form(**updates):
    result={f:'' for f in DATE_FIELDS}
    result.update(name='日期测试人物',sort='0',parent_id='0')
    result.update(updates)
    return result


@pytest.mark.parametrize('dates,expected',[
    ({'birth_solar_year':'1940','birth_solar_month':'2','birth_solar_day':'29'},'公历 1940年2月29日'),
    ({'birth_lunar_year':'1940','birth_lunar_month':'2','birth_lunar_day':'3','birth_lunar_leap':'1'},'农历 1940年闰二月初三'),
    ({'birth_lunar_year':'1940'},'农历 1940年'),
    ({'birth_solar_month':'2','birth_solar_day':'29'},'公历 2月29日（年份不详）'),
    ({},''),
])
def test_add_supports_independent_and_partial_dates(client,login,dates,expected):
    login()
    assert client.post('/f/a/tree/add',data=form(**dates)).status_code==302
    p=get_session().query(Person).filter_by(name='日期测试人物').one()
    assert p.birth_date_label==expected
    for field,value in dates.items():
        assert getattr(p,field)==int(value)
    assert p.birth_solar_year is None or p.birth_lunar_year is None


def test_both_calendars_round_trip_edit_and_clear(client,login):
    login()
    data=form(birth_solar_year='1940',birth_solar_month='2',birth_solar_day='29',
              birth_lunar_year='1940',birth_lunar_month='1',birth_lunar_day='22',birth_lunar_leap='1',
              death_solar_year='2001',death_solar_month='3',death_solar_day='1',
              death_lunar_year='2001',death_lunar_month='2',death_lunar_day='7')
    assert client.post('/f/a/tree/add',data=data).status_code==302
    p=get_session().query(Person).filter_by(name='日期测试人物').one();pid=p.id
    page=client.get(f'/f/a/tree/{pid}/edit').get_data(as_text=True)
    assert 'value="1940"' in page
    assert 'name="birth_lunar_leap" value="1" checked' in page
    edited=form(**{f:(str(v) if v is not None else '') for f,v in form_values(p).items() if not f.endswith('_leap')})
    edited['birth_lunar_leap']='1'
    edited['name']='已编辑人物';edited['birth_solar_day']='28'
    assert client.post(f'/f/a/tree/{pid}/edit',data=edited).status_code==302
    p=get_session().query(Person).filter_by(id=pid).one()
    assert p.birth_solar_day==28 and p.birth_lunar_day==22 and p.birth_lunar_leap
    assert p.death_solar_day==1 and p.death_lunar_day==7
    text=client.get(f'/f/a/person/{pid}').get_data(as_text=True)
    assert '公历 1940年2月28日 / 农历 1940年闰正月廿二' in text
    assert '公历 2001年3月1日 / 农历 2001年二月初七' in text
    assert client.post(f'/f/a/tree/{pid}/edit',data=form(name='已清空日期')).status_code==302
    p=get_session().query(Person).filter_by(id=pid).one()
    assert p.birth_year is None and p.death_year is None
    assert not p.birth_date_label and not p.death_date_label


@pytest.mark.parametrize('changes',[
    {'birth_solar_year':'1941','birth_solar_month':'2','birth_solar_day':'29'},
    {'birth_solar_month':'4','birth_solar_day':'31'},
    {'birth_lunar_day':'31','birth_lunar_month':'2'},
    {'birth_solar_day':'12'},
    {'birth_lunar_leap':'1'},
    {'birth_solar_year':'2000','death_solar_year':'1900'},
    {'birth_solar_year':'-10'},
    {'birth_solar_month':'13'},
    {'birth_solar_year':'abc'},
    {'alive':'1','death_solar_year':'2000'},
    {'birth_solar_year':'2001','birth_solar_month':'3','birth_solar_day':'2','death_solar_year':'2001','death_solar_month':'3','death_solar_day':'1'},
])
def test_invalid_dates_do_not_write_person_changes(client,login,changes):
    login()
    response=client.post('/f/a/tree/pa/edit',data=form(name='must-not-save',**changes))
    assert response.status_code==200
    assert '日期或排序有误' in response.get_data(as_text=True)
    assert get_session().query(Person).filter_by(id='pa').one().name=='Alpha Person'


def test_old_lunar_year_is_prefilled_without_conversion(client,login):
    p=get_session().query(Person).filter_by(id='pa').one()
    p.birth_year=1940;p.birth_calendar='lunar';get_session().commit()
    login()
    html=client.get('/f/a/tree/pa/edit').get_data(as_text=True)
    assert 'name="birth_lunar_year"' in html
    assert 'value="1940"' in html
    p=get_session().query(Person).filter_by(id='pa').one()
    assert form_values(p)['birth_solar_year']==''
    assert p.birth_date_label=='农历 1940年'


def test_migration_preserves_old_calendar_and_never_invents_months(tmp_path):
    from tests.test_migrations import old_database
    path=old_database(tmp_path)
    run_migrations('sqlite:///'+str(path))
    run_migrations('sqlite:///'+str(path))
    with sqlite3.connect(path) as db:
        row=db.execute('SELECT birth_year,birth_calendar,birth_lunar_year,birth_solar_year,birth_lunar_month,birth_lunar_day,death_solar_year,death_lunar_year FROM persons').fetchone()
        assert row==(1940,'lunar',1940,None,None,None,2001,None)


def test_sync_year_cannot_overwrite_precise_dual_dates(client,login):
    p=get_session().query(Person).filter_by(id='pa').one()
    p.birth_solar_year=1940;p.birth_solar_month=2;p.birth_solar_day=29
    p.birth_lunar_year=1940;p.birth_lunar_month=1;p.birth_lunar_day=22
    p.birth_year=1940;p.birth_calendar='solar';get_session().commit()
    login()
    packet={'type':'tree_upsert','clientId':'conflicting-year','payload':{'persons':[{'fullName':'Alpha Person','birthYear':1941}]}}
    response=client.post('/api/sync',json={'family_id':'a','packet':packet})
    assert response.status_code==400
    p=get_session().query(Person).filter_by(id='pa').one()
    assert (p.birth_solar_year,p.birth_solar_day,p.birth_lunar_day)==(1940,29,22)
    packet['clientId']='matching-year';packet['payload']['persons'][0]['birthYear']=1940
    assert client.post('/api/sync',json={'family_id':'a','packet':packet}).get_json()['applied']
    assert get_session().query(Person).filter_by(id='pa').one().birth_lunar_day==22


def test_partial_update_keeps_other_calendar_and_date_precision(client,login):
    p=get_session().query(Person).filter_by(id='pa').one()
    p.birth_solar_year=1940;p.birth_solar_month=2;p.birth_solar_day=29
    p.birth_lunar_year=1940;p.birth_lunar_month=1;p.birth_lunar_day=22
    p.birth_year=1940;p.birth_calendar='solar';get_session().commit()
    login()
    assert client.post('/f/a/tree/pa/edit',data={'name':'Alpha Person','birth_solar_day':'28'}).status_code==302
    p=get_session().query(Person).filter_by(id='pa').one()
    assert (p.birth_solar_year,p.birth_solar_month,p.birth_solar_day,p.birth_lunar_day)==(1940,2,28,22)


def test_sync_still_fills_year_only_record_and_rejects_alive_death_conflict(client,login):
    login()
    packet={'type':'tree_upsert','clientId':'year-only','payload':{'persons':[{'fullName':'Alpha Person','birthYear':1940}]}}
    assert client.post('/api/sync',json={'family_id':'a','packet':packet}).get_json()['applied']
    p=get_session().query(Person).filter_by(id='pa').one()
    assert p.birth_solar_year==1940 and p.birth_solar_month is None
    packet['clientId']='bad-death';packet['payload']['persons'][0].update(deathYear=1930)
    assert client.post('/api/sync',json={'family_id':'a','packet':packet}).status_code==400
    assert get_session().query(Person).filter_by(id='pa').one().death_year is None
    packet['clientId']='bad-alive';packet['payload']['persons'][0].update(deathYear=2000,alive=True)
    assert client.post('/api/sync',json={'family_id':'a','packet':packet}).status_code==400
    assert get_session().query(Person).filter_by(id='pa').one().death_year is None
