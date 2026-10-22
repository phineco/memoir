import datetime
from models import Draft,Interview,get_session
from reporting import current_period


def test_late_draft_published_in_current_week_and_timestamp_stable(client,login):
    login();s=get_session();iv=s.query(Interview).filter_by(id='draft-a').one();iv.create_date=datetime.datetime.now()-datetime.timedelta(days=14);s.commit()
    assert client.post('/f/a/story/draft-a/publish').status_code==302
    first=get_session().query(Interview).filter_by(id='draft-a').one().published_at
    year,week=current_period();data=client.get(f'/api/weekly-report?family_id=a&year={year}&week={week}').get_json()
    story=next(x for x in data['stories'] if x['id']=='draft-a')
    assert not story['publication_time_inferred']
    client.post('/f/a/story/draft-a/publish')
    assert get_session().query(Interview).filter_by(id='draft-a').one().published_at==first
    assert client.post('/f/a/story/draft-a/edit',data={'topic':'revised','content':'<p>changed</p>','revision_reason':'checked','base_version':'1'}).status_code==302
    assert get_session().query(Interview).filter_by(id='draft-a').one().published_at==first
    data=client.get(f'/api/weekly-report?family_id=a&year={year}&week={week}').get_json()
    assert 'draft-a' in {r['id'] for r in data['revisions']}


def test_legacy_timestamps_remain_explicit_estimates(client,login):
    login();data=client.get('/api/weekly-report?family_id=a').get_json()
    story=next(x for x in data['stories'] if x['id']=='public-a')
    assert story['publication_time_inferred']
    assert get_session().query(Interview).filter_by(id='public-a').one().published_at is None


def test_publication_clock_follows_configured_timezone(monkeypatch):
    import reporting
    from zoneinfo import ZoneInfo
    monkeypatch.setattr(reporting.Config,'APP_TIMEZONE','America/Los_Angeles')
    before=datetime.datetime.now(ZoneInfo('America/Los_Angeles')).replace(tzinfo=None)
    value=reporting.local_now()
    after=datetime.datetime.now(ZoneInfo('America/Los_Angeles')).replace(tzinfo=None)
    assert before<=value<=after and value.tzinfo is None


def test_newly_published_old_draft_appears_first_in_story_list(client,login):
    login();s=get_session();s.query(Interview).filter_by(id='draft-a').one().create_date=datetime.datetime.now()-datetime.timedelta(days=40);s.commit()
    client.post('/f/a/story/draft-a/publish')
    html=client.get('/f/a/stories').get_data(as_text=True)
    assert html.index('/story/draft-a')<html.index('/story/public-a')
