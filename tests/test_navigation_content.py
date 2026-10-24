import re
from html import unescape
from urllib.parse import parse_qs, urlsplit

import pytest

from models import FamilyMember, Interview, InterviewPerson, Person, Photo, get_session


def test_personal_about_own_and_drafts_have_distinct_permission_scopes(client,login):
    s=get_session();s.get(Person,'pa').user_id='owner-a'
    s.get(Interview,'public-a').person_id='pa'
    s.get(Interview,'specific-a').narrator_person_id='pa'  # Narrator alone is not the subject.
    s.add(InterviewPerson(id='about-link',interview_id='private-a',person_id='pa',role='related'))
    s.add(Interview(id='hidden-other',family_id='a',author_id='member-a',person_id='pa',topic='Hidden other author',publish_status='published',visibility='private'))
    s.add(Interview(id='former-own',family_id='b',author_id='owner-a',topic='Former family own',publish_status='published',visibility='public'))
    # A broken foreign relation must not manufacture a story about the current user.
    s.add(InterviewPerson(id='foreign-link',interview_id='public-b',person_id='pa',role='related'))
    s.commit();login()
    own=client.get('/account/stories?kind=own').get_data(as_text=True)
    about=client.get('/account/stories?kind=about').get_data(as_text=True)
    drafts=client.get('/account/drafts').get_data(as_text=True)
    assert all(title in own for title in ['public-a','private-a','specific-a'])
    assert 'draft-a' not in own
    assert 'public-a' in about and 'private-a' in about and 'specific-a' not in about
    assert 'draft-a' in drafts and 'public-a' not in drafts
    for body in (own,about,drafts):
        assert 'Hidden other author' not in body and 'Former family own' not in body and 'Beta Secret Family' not in body
    assert client.get('/account/stories?scope_family=b').status_code==404
    assert client.get('/account/stories?kind=bad').status_code==400
    assert client.get('/account/stories?page=bad').status_code==400
    s.get(FamilyMember,'ma').del_flag=1;s.commit()
    assert 'public-a' not in client.get('/account/stories?kind=about').get_data(as_text=True)


def test_personal_lists_paginate_and_preserve_family_and_search(client,login):
    s=get_session()
    for index in range(25):s.add(Interview(id=f'own-{index:02}',family_id='a',author_id='owner-a',topic=f'Unique list {index:02}',publish_status='published',visibility='public'))
    s.commit();login()
    first=client.get('/account/stories?kind=own&scope_family=a&q=Unique').get_data(as_text=True)
    second=client.get('/account/stories?kind=own&scope_family=a&q=Unique&page=2').get_data(as_text=True)
    assert first.count('class="card record-card"')==20 and second.count('class="card record-card"')==5
    assert 'scope_family=a' in first and 'q=Unique' in first and 'page=2' in first
    assert '共 0 篇' in client.get('/account/stories?q=%25').get_data(as_text=True)
    legacy=client.get('/f/a/drafts');assert legacy.status_code==302
    assert urlsplit(legacy.location).path=='/account/drafts'


def test_person_context_and_cross_family_return_do_not_guess_narrator(client,login):
    login()
    page=client.get('/f/a/person/pa?section=stories').get_data(as_text=True)
    assert 'aria-label="人物内容"' in page and 'subject_id=pa' in page
    form=client.get('/f/a/write?subject_id=pa&mode=accompany').get_data(as_text=True)
    assert 'value="pa" selected' in form
    assert client.get('/f/a/write?subject_id=pb').status_code==400
    assert client.get('/f/a/person/pa?section=bad').status_code==400
    s=get_session();s.add(FamilyMember(id='cross-family',family_id='b',user_id='owner-a',role='member'));s.commit()
    target='/account/stories?kind=own&family_id=a'
    body=unescape(client.get('/f/b/story/public-b',query_string={'return_to':target}).get_data(as_text=True))
    assert 'data-restore-list href="'+target+'"' in body
    s.get(FamilyMember,'ma').del_flag=1;s.commit()
    body=unescape(client.get('/f/b/story/public-b',query_string={'return_to':target}).get_data(as_text=True))
    assert 'data-restore-list href="/f/b/stories"' in body


def test_album_person_time_filters_preserve_uncertain_dates(client,login):
    s=get_session()
    for pid,year,month,day in [('year',1985,None,None),('month',1985,6,None),('day',1985,6,12),('later',1986,1,1),('unknown',None,None,None)]:
        s.add(Photo(id=pid,family_id='a',person_id='pa',photo_year=year,photo_month=month,photo_day=day,title=pid,location='老家',uploaded_by='owner-a'))
    s.add(Photo(id='foreign',family_id='b',person_id='pb',photo_year=1985,title='Foreign photo'))
    s.commit();login()
    base='/f/a/album/choices?person=pa&location=老家&uploader=user:owner-a'
    result=client.get(base+'&date_from=1985-06-13&date_to=1985-06-14').json
    assert {p['id'] for p in result['photos']}=={'year','month'}
    result=client.get(base+'&date_from=1985-06-12&date_to=1985-06-12&include_unknown=1').json
    assert {p['id'] for p in result['photos']}=={'year','month','day','unknown'}
    result=client.get(base+'&sort=oldest').json
    assert result['photos'][0]['id']=='year' and result['photos'][-1]['id']=='unknown'
    for suffix in ['person=pb','date_from=no','date_from=2026-01-01&date_to=2025-01-01','sort=bad','view=bad','include_unknown=bad']:
        assert client.get('/f/a/album?'+suffix).status_code==400
    assert client.get('/f/a/album?view=grid').status_code==200


def test_album_preview_crosses_pages_in_the_same_filtered_result(client,login):
    s=get_session()
    for index in range(26):s.add(Photo(id=f'preview-{index:02}',family_id='a',person_id='pa',title=f'Photo {index}',location='old home',photo_year=1980+index,uploaded_by='owner-a'))
    s.commit();login()
    source='/f/a/album?person=pa&location=old+home&view=grid&sort=newest'
    body=unescape(client.get('/f/a/album/preview-02',query_string={'return_to':source}).get_data(as_text=True))
    target=re.search(r'href="([^"]+)">下一张</a>',body)[1]
    parts=urlsplit(target);assert parts.path.endswith('/preview-01')
    returned=parse_qs(parts.query)['return_to'][0]
    filters=parse_qs(urlsplit(returned).query)
    assert filters['page']==['2'] and filters['person']==['pa'] and filters['view']==['grid'] and filters['location']==['old home']
    assert '照片人物' in body and '上传人：Alpha Owner' in body


def test_organised_tools_help_and_account_do_not_claim_unbuilt_features(client,login):
    login()
    more=client.get('/f/a/more').get_data(as_text=True)
    assert '回忆工具' in more and '整理与保存' in more and '导出家庭可见文章' in more
    assert '尚未开放' in more and '通知留资' not in more
    account=client.get('/account?family_id=a').get_data(as_text=True)
    for label in ['关于我的故事','我记录的故事','我的草稿','我的声音','我的 AI 记忆','隐私申请','显示设置','我的家庭']:
        assert label in account
    assert '我的收藏' not in account and '采访录音档案' not in account
    help_body=client.get('/guide?family_id=a').get_data(as_text=True)
    for identifier in ['writing','reading','people','photos','voice','members','export','troubleshooting']:
        assert f'id="{identifier}"' in help_body


def test_nested_person_photo_return_retains_the_original_family_view(client,login):
    s=get_session();s.add(Photo(id='linked-photo',family_id='a',person_id='pa',title='Linked photo'));s.commit()
    login()
    source='/f/a/person/pa?section=photos&return_to=%2Ff%2Fa%3Fview%3Dtree'
    body=unescape(client.get(source).get_data(as_text=True))
    href=re.search(r'href="([^"]*/album/linked-photo[^\"]*)"',body)[1]
    target=parse_qs(urlsplit(href).query)['return_to'][0]
    assert target==source
    assert parse_qs(urlsplit(target).query)['return_to']==['/f/a?view=tree']
