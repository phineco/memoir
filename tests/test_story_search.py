import datetime as dt
import re
import sqlite3

import pytest

from migrate import run_migrations
from models import Draft,FamilyMember,Interview,Quote,get_session
from search_index import plain_text
from tests.test_migrations import old_database


def ids(response):
    assert response.status_code==200
    return re.findall(r'class="card" href="/f/a/story/([^"#?]+)"',response.get_data(as_text=True))


def test_search_permissions_apply_to_results_and_counts(client,login):
    s=get_session()
    for draft in s.query(Draft):draft.content='<p>shared needle</p>'
    s.commit()
    for user,expected in [('owner-a',{'public-a','private-a','specific-a','draft-a'}),('member-a',{'public-a','specific-a'})]:
        login(user);response=client.get('/f/a/stories?q=shared')
        assert set(ids(response))==expected
        assert '共 %d 篇'%len(expected) in response.get_data(as_text=True)
        for identifier in expected:assert client.get('/f/a/story/'+identifier).status_code==200
    login('owner-b');assert client.get('/f/a/stories?q=shared').status_code==404
    login();s=get_session();s.query(FamilyMember).filter_by(id='ma').update({FamilyMember.del_flag:1});s.commit()
    assert client.get('/f/a/stories?q=shared').status_code==404


def test_search_normalized_current_body_and_active_quotes_only(client,login):
    login();s=get_session()
    s.query(Draft).filter_by(id='d-public-a').one().content='<p>院子里有紫藤<b>花</b>。</p><p class="HIDDEN_TAG_TERM">后半段</p>'
    s.add(Draft(id='old-version',interview_id='public-a',version=0,is_current=False,content='OLD_REVISION_TERM'))
    s.add_all([Quote(id='matching-q1',interview_id='public-a',text='UNIQUE_QUOTE'),Quote(id='matching-q2',interview_id='public-a',text='UNIQUE_QUOTE'),Quote(id='dropped',interview_id='public-a',text='DROPPED_TERM',status='dropped')]);s.commit()
    assert ids(client.get('/f/a/stories?q=紫藤花'))==['public-a']
    assert ids(client.get('/f/a/stories?q=UNIQUE_QUOTE'))==['public-a']
    for term in ('OLD_REVISION_TERM','HIDDEN_TAG_TERM','DROPPED_TERM'):
        assert ids(client.get('/f/a/stories',query_string={'q':term}))==[]


def test_literal_percent_and_underscore_are_not_wildcards(client,login):
    login();s=get_session();s.query(Interview).filter_by(id='public-a').one().topic='100% retained_A';s.commit()
    assert ids(client.get('/f/a/stories?q=%25'))==['public-a']
    assert ids(client.get('/f/a/stories?q=retained_A'))==['public-a']
    assert ids(client.get('/f/a/stories?q=retained_B'))==[]


def test_people_interval_publication_and_unknown_date_rules(client,login):
    login();s=get_session();story=s.query(Interview).filter_by(id='public-a').one()
    s.query(Interview).filter(Interview.id!='public-a').update({Interview.create_date:dt.datetime(2020,1,1)})
    story.person_id='pa';story.narrator_person_id='pa';story.period_start=dt.date(1980,1,1);story.period_end=dt.date(1990,12,31);story.published_at=dt.datetime(2026,10,23,23,59)
    s.commit()
    assert ids(client.get('/f/a/stories?subject=pa&narrator=pa&period_from=1985-01-01&period_to=1986-01-01'))==['public-a']
    assert ids(client.get('/f/a/stories?published_from=2026-10-23&published_to=2026-10-23'))==['public-a']
    assert 'draft-a' not in ids(client.get('/f/a/stories?published_from=2000-01-01'))
    assert client.get('/f/a/stories?subject=pb').status_code==400


def test_pagination_preserves_conditions_and_has_stable_distinct_rows(client,login):
    login();s=get_session()
    for index in range(45):s.add(Interview(id='paged-%02d'%index,family_id='a',topic='paged-match',publish_status='published',visibility='public',published_at=dt.datetime(2026,10,23)))
    s.commit()
    first=client.get('/f/a/stories?q=paged-match');second=client.get('/f/a/stories?q=paged-match&page=2')
    assert len(ids(first))==20 and len(ids(second))==20
    assert not set(ids(first))&set(ids(second))
    assert len(ids(client.get('/f/a/stories?q=paged-match&page=3')))==5
    assert 'q=paged-match' in second.get_data(as_text=True)


@pytest.mark.parametrize('query',['page=0','page=bad','sort=invalid','period_from=bad','period_from=2026-10-24&period_to=2026-10-23'])
def test_invalid_filters_are_rejected(client,login,query):
    login();assert client.get('/f/a/stories?'+query).status_code==400


def test_search_migration_backfills_readable_text_and_is_repeatable(tmp_path):
    database=old_database(tmp_path)
    with sqlite3.connect(database) as conn:
        conn.execute("INSERT INTO drafts (id,content) VALUES ('old','<p>紫藤<b>花</b></p>')")
    url='sqlite:///'+str(database)
    before=database.read_bytes();run_migrations(url,dry_run=True);assert before==database.read_bytes()
    run_migrations(url);run_migrations(url)
    with sqlite3.connect(database) as conn:
        assert conn.execute("SELECT content,search_text FROM drafts WHERE id='old'").fetchone()==('<p>紫藤<b>花</b></p>','紫藤花')
    assert plain_text('<p>visible<script>secret</script></p>')=='visible'
