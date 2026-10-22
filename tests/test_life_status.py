import ai
from models import Person, get_session


def test_name_only_remains_unknown(client,login):
    login();assert client.post('/f/a/tree/add',data={'name':'Unknown Relative'}).status_code==302
    p=get_session().query(Person).filter_by(name='Unknown Relative').one()
    assert p.life_status=='unknown' and p.alive is None
    assert 'Unknown Relative（关系未知，出生：不详；生存状态未知' in ai.family_knowledge('a','owner-a')


def test_explicit_alive_deceased_and_conflict(client,login):
    login()
    for state in ('alive','deceased','unknown'):
        assert client.post('/f/a/tree/pa/edit',data={'name':'Alpha Person','life_status':state}).status_code==302
        assert get_session().query(Person).filter_by(id='pa').one().life_state==state
    response=client.post('/f/a/tree/pa/edit',data={'name':'bad','life_status':'alive','death_solar_year':'2000'})
    assert '健在与去世日期' in response.get_data(as_text=True)
    assert get_session().query(Person).filter_by(id='pa').one().name=='Alpha Person'


def test_ambiguous_legacy_false_is_not_deceased(app):
    s=get_session();p=s.query(Person).filter_by(id='pa').one();p.alive=False;s.commit()
    assert p.life_state=='unknown'
    p.death_year=2000;s.commit();assert p.life_state=='deceased'


def test_partial_profile_update_keeps_confirmed_life_state(client,login):
    login();s=get_session();p=s.query(Person).filter_by(id='pa').one();p.life_status='alive';p.alive=True;s.commit()
    assert client.post('/f/a/tree/pa/edit',data={'name':'Alpha Person','birth_solar_year':'1940'}).status_code==302
    assert get_session().query(Person).filter_by(id='pa').one().life_state=='alive'
