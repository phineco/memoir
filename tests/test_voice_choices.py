"""Voice choices use real ACL/version rules and a synthetic provider only."""
import datetime as dt
import hashlib
import re

import pytest

from models import Person,User,Interview,VoiceProfile,VoiceConsent,VoiceAudio,VoiceCharge,FamilyMember,get_session
from tests.test_family_voices import voice,token
from voice_worker import process_one
from voices import CONSENT_VERSION,story_content,story_context


def add_ready_voice(session,provider,person,identifier):
    model='cosyvoice-v3.5-flash'
    remote=model+'-'+identifier+'-synthetic'
    profile_id=hashlib.sha256(identifier.encode()).hexdigest()[:32]
    row=VoiceProfile(id=profile_id,person_id=person.id,family_id=person.family_id,model=model,prefix=identifier,
                     subject_state=person.life_state,subject_user_id=person.user_id,status='ready',epoch=1,
                     reviewed_at=dt.datetime.now(),reviewed_by='synthetic-operator',provider_voice_id=remote)
    session.add(row)
    session.add(VoiceConsent(id='consent-'+identifier,profile_id=profile_id,epoch=1,user_id=person.user_id,
                            relation='本人',version=CONSENT_VERSION))
    provider.voices[remote]=model
    return row


@pytest.fixture
def choices(voice):
    s=get_session()
    first=add_ready_voice(s,voice,s.get(Person,'pa'),'voiceone')
    person=Person(id='pa2',family_id='a',name='Second Narrator',user_id='member-a',life_status='alive')
    s.add(person)
    second=add_ready_voice(s,voice,person,'voicetwo')
    story=s.get(Interview,'public-a');story.narrator_person_id='pa2';story.person_id='pa'
    s.commit()
    return first.id,second.id


def context(app):
    with app.app_context():return story_context(get_session().get(Interview,'public-a'),get_session().get(User,'owner-a'))


def test_prefers_available_narrator_not_subject_or_first_family_voice(choices,voice,app,client,login):
    login();ctx=context(app)
    assert ctx['voice_default']==choices[1]
    assert [row.id for row in ctx['voice_profiles']]==[choices[1],choices[0]]
    body=client.get('/f/a/story/public-a').get_data(as_text=True)
    assert re.search(r'value="'+choices[1]+r'"[^>]*selected',body)
    assert 'Second Narrator（讲述者）' in body and '普通朗读（设备声音）' in body
    assert body.count('id="storyReadBtn"')==1
    assert voice.creates==voice.syntheses==get_session().query(VoiceCharge).count()==0
    for narrator in (None,'pa-missing','pb'):
        get_session().get(Interview,'public-a').narrator_person_id=narrator;get_session().commit()
        assert context(app)['voice_default']==''  # Never impersonate an arbitrary relative.


@pytest.mark.parametrize('invalid',['revoked','unreviewed','pending','deleted','rebound','removed','deceased','foreign'])
def test_invalid_narrator_is_not_offered_and_falls_back_to_device(choices,voice,app,client,login,invalid):
    s=get_session();row=s.get(VoiceProfile,choices[1]);person=s.get(Person,'pa2')
    if invalid=='revoked':s.query(VoiceConsent).filter_by(profile_id=row.id).one().revoked_at=dt.datetime.now()
    elif invalid=='unreviewed':row.reviewed_at=None
    elif invalid=='pending':row.status='processing'
    elif invalid=='deleted':row.del_flag=1
    elif invalid=='rebound':person.user_id='owner-a'
    elif invalid=='removed':s.query(FamilyMember).filter_by(user_id='member-a',family_id='a').one().del_flag=1
    elif invalid=='deceased':person.life_status=row.subject_state='deceased'
    elif invalid=='foreign':row.family_id='b'
    s.commit();login();ctx=context(app)
    assert ctx['voice_default']==''
    assert [row.id for row in ctx['voice_profiles']]==[choices[0]]
    body=client.get('/f/a/story/public-a').get_data(as_text=True)
    assert 'data-name="Second Narrator"' not in body and '<option value="" selected>' in body
    csrf=token(client,'/account/voices');_,_,stamp=story_content(s.get(Interview,'public-a'))
    response=client.post('/f/a/story/public-a/voice',json={'profile_id':choices[1],'stamp':stamp,'authorize':'yes'},headers={'X-CSRF-Token':csrf})
    assert response.status_code==404 and voice.syntheses==0


def test_no_available_family_voice_keeps_reading_and_self_setup(voice,app,client,login):
    login();body=client.get('/f/a/story/public-a').get_data(as_text=True)
    assert '暂无可用的家人音色' in body and '普通朗读（设备声音）' in body
    assert '/account/voices?family_id=a' in body
    assert get_session().query(VoiceProfile).count()==0
    app.config['VOICE_ENABLED']=False
    body=client.get('/f/a/story/public-a').get_data(as_text=True)
    assert 'id="voice-choice"' not in body and 'id="storyReadBtn"' in body


def test_different_people_have_separate_cache_and_current_reader_permissions(choices,voice,app,client,login):
    login();csrf=token(client,'/account/voices')
    def request(profile_id,story='public-a',authorize=True):
        _,_,stamp=story_content(get_session().get(Interview,story))
        return client.post('/f/a/story/'+story+'/voice',json={'profile_id':profile_id,'stamp':stamp,**({'authorize':'yes'} if authorize else {})},headers={'X-CSRF-Token':csrf})
    first=request(choices[0]);second=request(choices[1])
    assert first.status_code==second.status_code==202 and first.json['id']!=second.json['id']
    with app.app_context():assert process_one() and process_one()
    for profile_id in choices:assert request(profile_id).status_code==200
    assert voice.syntheses==get_session().query(VoiceCharge).count()==2
    assert {row.profile_id for row in get_session().query(VoiceAudio)}==set(choices)
    login('member-a');csrf=token(client,'/account/voices')
    assert request(choices[1],authorize=False).status_code==200
    assert request(choices[1],story='private-a',authorize=False).status_code==404
    assert request(choices[1],story='specific-a',authorize=False).status_code==403
    assert voice.syntheses==2
