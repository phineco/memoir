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
