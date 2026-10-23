import datetime
import hashlib
import io
import json
import re
import zipfile

import pytest

import article_exports
from models import Draft, FamilyMember, Interview, User, get_session

PATH = '/f/a/exports/articles'


def download(client, scope='own', **extra):
    page = client.get(PATH+'?scope='+scope)
    token = re.search(r'name="csrf_token" value="([^"]+)"',page.get_data(as_text=True))
    return client.post(PATH, data=dict(csrf_token=token.group(1) if token else '', scope=scope, mode='all', **extra))


def unpack(response):
    assert response.status_code == 200
    assert response.mimetype == 'application/zip'
    assert response.headers['Cache-Control'] == 'private, no-store'
    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    assert 'attachment;' in response.headers['Content-Disposition']
    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        assert set(archive.namelist()) == {'index.html','README.txt','manifest.json','articles.json'}
        files = {name:archive.read(name) for name in archive.namelist()}
    manifest = json.loads(files['manifest.json'])
    for name, detail in manifest['files'].items():
        assert hashlib.sha256(files[name]).hexdigest() == detail['sha256']
        assert len(files[name]) == detail['bytes']
    return files, json.loads(files['articles.json'])


def test_own_export_contains_current_owned_drafts_and_private_stories_only(client, login):
    login()
    s=get_session()
    s.add(Draft(id='old-public', interview_id='public-a', version=0, is_current=False,
                content='HISTORY-MUST-NOT-EXPORT'))
    s.commit()
    files,data=unpack(download(client))
    assert {item['id'] for item in data['articles']} == {'public-a','private-a','specific-a','draft-a'}
    assert data['export']['article_count']==4 and data['export']['eligible_total']==4
    assert not data['export']['includes_media'] and not data['export']['includes_history']
    assert all(item['version']==1 for item in data['articles'])
    combined=b'\n'.join(files.values())
    assert b'HISTORY-MUST-NOT-EXPORT' not in combined and b'content-public-b' not in combined
    assert b'password_hash' not in combined and b'storage_path' not in combined and b'provider_voice_id' not in combined
    assert '<meta http-equiv="Content-Security-Policy"' in files['index.html'].decode()


def test_family_export_never_includes_others_private_specific_or_unpublished(client, login):
    login()
    files,data=unpack(download(client,'family'))
    assert [item['id'] for item in data['articles']] == ['public-a']
    assert data['export']['scope']=='family'
    assert b'content-private-a' not in files['articles.json']
    login('member-a')
    assert client.get('/f/a/story/specific-a').status_code==200
    assert client.get(PATH+'?scope=family').status_code==403
    assert client.post(PATH,data={'scope':'family'}).status_code==403
    assert 'specific-a' not in client.get(PATH).get_data(as_text=True)
    assert download(client).status_code==400  # Being a named reader does not grant another author's export.


def test_export_requires_login_current_membership_and_csrf(client,login):
    assert client.get(PATH).status_code==302
    login()
    assert client.get('/f/b/exports/articles').status_code==404
    assert client.post(PATH,data={'scope':'own','mode':'all'}).status_code==400
    assert client.get(PATH+'?scope=all').status_code==400
    for bad in ['0','-1','not-a-number','9999']:
        assert client.get(PATH+'?batch='+bad).status_code==400
    s=get_session();s.query(FamilyMember).filter_by(id='ma').one().del_flag=1;s.commit()
    assert client.get(PATH).status_code==404
    assert client.post(PATH,data={'scope':'own','mode':'all'}).status_code==404
    assert 'Alpha Family' not in client.get('/account/exports').get_data(as_text=True)
    assert client.get('/account/exports?family_id=a').status_code==404


def test_offline_file_is_safe_and_preserves_uncertain_dates_and_metadata(client,login):
    login()
    s=get_session();story=s.query(Interview).filter_by(id='public-a').one()
    story.topic='<img src="https://example.test/track" onerror="alert(1)">'
    story.person_id='pa';story.narrator_person_id='pa'
    story.period_start=datetime.date(1960,1,1);story.period_end=datetime.date(1960,12,31);story.period_precision='year'
    story.create_date=datetime.datetime(2020,1,2,3,4,5);story.published_at=None
    s.query(Draft).filter_by(id='d-public-a').one().content='<h2>一段回忆</h2><p><strong>真实文字</strong></p><script>alert(2)</script><img src="https://example.test/track"><audio src="private-url"></audio>'
    s.commit()
    files,data=unpack(download(client,'family'))
    item=data['articles'][0];html=files['index.html'].decode()
    assert item['period_label']=='1960年'
    assert item['period_precision']=='year' and item['published_at'] is None
    assert item['publication_estimate']=='2020-01-02T03:04:05'
    assert item['subject']=='Alpha Person' and item['narrator']=='Alpha Person'
    assert '按录入时间推定' in html and '<strong>真实文字</strong>' in html
    assert '<img' not in html and '<script' not in html and '<audio' not in html
    assert '&lt;img' in html and '1960-01-01' not in html


@pytest.mark.parametrize('change,expected', [('removed',404),('disabled',404),('role',403),('visibility',409),('revision',409)])
def test_permissions_and_revision_are_rechecked_after_build(client,login,monkeypatch,change,expected):
    login()
    original=article_exports.build_archive
    def during_build(records,info):
        result=original(records,info)
        s=get_session()
        if change=='removed':s.query(FamilyMember).filter_by(id='ma').one().del_flag=1
        elif change=='disabled':s.query(User).filter_by(id='owner-a').one().del_flag=1
        elif change=='role':s.query(FamilyMember).filter_by(id='ma').one().role='member'
        elif change=='visibility':s.query(Interview).filter_by(id='public-a').one().visibility='private'
        else:s.query(Draft).filter_by(id='d-public-a').one().content='<p>Changed while packaging</p>'
        s.commit()
        return result
    monkeypatch.setattr(article_exports,'build_archive',during_build)
    response=download(client,'family')
    assert response.status_code==expected and response.mimetype!='application/zip'


@pytest.mark.parametrize('broken',['missing','duplicate'])
def test_broken_current_version_never_reports_complete_export(client,login,broken):
    login();s=get_session()
    if broken=='missing':s.query(Draft).filter_by(id='d-public-a').one().del_flag=1
    else:s.add(Draft(id='second-current',interview_id='public-a',version=2,is_current=True,content='Ambiguous'))
    s.commit()
    response=download(client,'family')
    assert response.status_code==409 and response.mimetype!='application/zip'


def test_bounded_batches_and_oversize_are_explicit(client,login,monkeypatch):
    login()
    monkeypatch.setattr(article_exports,'BATCH_SIZE',2)
    monkeypatch.setattr(article_exports,'MAX_ALL_STORIES',3)
    assert download(client).status_code==413
    page=client.get(PATH).get_data(as_text=True)
    token=re.search(r'name="csrf_token" value="([^"]+)"',page).group(1)
    ids=set()
    for batch in [1,2]:
        response=client.post(PATH,data={'csrf_token':token,'scope':'own','mode':'batch','batch':str(batch)})
        files,data=unpack(response)
        assert 'own-batch-'+str(batch)+'-' in response.headers['Content-Disposition']
        assert data['export']['eligible_total']==4 and data['export']['article_count']==2
        assert data['export']['batch']==batch and '不是全部范围' in files['index.html'].decode()
        current={item['id'] for item in data['articles']};assert not current&ids;ids|=current
    assert len(ids)==4
    monkeypatch.setattr(article_exports,'MAX_STORY_BYTES',5)
    assert download(client,'family').status_code==413
