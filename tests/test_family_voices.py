import datetime as dt
import io
import re
import struct
import shutil
import wave

import pytest

from models import (Draft,FamilyMember,Interview,Person,VoiceAudio,VoiceAudit,VoiceCharge,
                    VoiceConsent,VoiceProfile,get_session)
from voice_provider import CosyVoiceProvider,VoiceError,get_provider
from voice_worker import process_one
from voices import CONSENT_VERSION,story_content
import voice_storage


def wav(seconds=10):
    output=io.BytesIO()
    with wave.open(output,'wb') as audio:
        audio.setparams((1,2,24000,0,'NONE','not compressed'))
        audio.writeframes(struct.pack('<hh',1200,-1200)*int(12000*seconds))
    return output.getvalue()


class FakeProvider:
    def __init__(self):self.voices={};self.creates=0;self.syntheses=0;self.fail_delete=False;self.on_synthesis=None;self.on_create=None
    def create(self,sample,model,prefix):
        self.creates+=1;identifier=model+'-'+prefix+'-synthetic';self.voices[identifier]=model
        if self.on_create:self.on_create(identifier)
        return identifier
    def query(self,voice):return 'OK',self.voices[voice]
    def list(self,prefix):return [key for key in self.voices if '-'+prefix+'-' in key]
    def delete(self,voice):
        if self.fail_delete:raise VoiceError('provider_unavailable')
        self.voices.pop(voice,None)
        return 'synthetic-delete-receipt'
    def synthesize(self,voice,model,text):
        assert voice in self.voices and self.voices[voice]==model
        self.syntheses+=1
        if self.on_synthesis:self.on_synthesis()
        return wav(1)


@pytest.fixture
def voice(app):
    fake=FakeProvider()
    app.config.update(VOICE_ENABLED=True,VOICE_TEST_PROVIDER=fake,VOICE_FAMILY_LIMITS={'a':{'voices':2,'monthly_characters':50000}},OPERATIONS_USER_IDS=('outsider',),VOICE_FFMPEG=shutil.which('ffmpeg') or 'ffmpeg',VOICE_FFPROBE=shutil.which('ffprobe') or 'ffprobe')
    s=get_session();person=s.get(Person,'pa');person.life_status='alive';person.user_id='owner-a';s.commit()
    return fake


def token(client,path):
    response=client.get(path);assert response.status_code==200
    return re.search(r'name="csrf_token" value="([^"]+)"',response.get_data(as_text=True)).group(1)


def profile():return get_session().query(VoiceProfile).one()


def start(client):
    csrf=token(client,'/f/a/person/pa/voice')
    assert client.post('/f/a/person/pa/voice',data={'csrf_token':csrf,'action':'start'}).status_code==302
    return csrf


def consent(client,csrf):
    return client.post('/f/a/person/pa/voice',data=dict(csrf_token=csrf,action='consent',version=CONSENT_VERSION,adult='yes',agree='yes'))


def review(app):
    operator=app.test_client()
    with operator.session_transaction() as state:state['user_id']='outsider'
    csrf=token(operator,'/operations/voices')
    return operator.post('/operations/voices',data=dict(csrf_token=csrf,profile_id=profile().id,action='review',identity_verified='yes',provider_authorized='yes',scope_verified='yes',evidence_ref='synthetic-evidence-001'))


def ready(app,client,login):
    login();csrf=start(client);assert consent(client,csrf).status_code==302;assert review(app).status_code==302
    response=client.post('/f/a/person/pa/voice',data=dict(csrf_token=csrf,action='sample',quality='yes',start='0',length='10',sample=(io.BytesIO(wav()),'clip.wav')))
    assert response.status_code==302,response.get_data(as_text=True)
    with app.app_context():assert process_one()
    assert profile().status=='ready'
    return csrf


def request_audio(client,csrf,story='public-a',authorize=True,**extra):
    draft,text,digest=story_content(get_session().get(Interview,story))
    payload=dict(profile_id=profile().id,stamp=digest,**extra)
    if authorize:payload['authorize']='yes'
    return client.post('/f/a/story/'+story+'/voice',json=payload,headers={'X-CSRF-Token':csrf})


def test_feature_off_has_no_new_entry_or_provider_calls(app,client,login):
    login();assert client.get('/f/a/person/pa/voice').status_code==404
    assert '管理声音与授权' not in client.get('/f/a/person/pa').get_data(as_text=True)
    assert client.post('/f/a/story/public-a/voice',json={}).status_code==404
    assert get_session().query(VoiceProfile).count()==0


def test_admin_cannot_consent_for_someone_else_and_no_sample_before_review(voice,app,client,login):
    login();csrf=start(client)
    assert client.post('/f/a/person/pa/voice',data=dict(csrf_token=csrf,action='sample',quality='yes')).status_code==409
    person=get_session().get(Person,'pa');person.user_id='member-a';get_session().commit()
    assert consent(client,csrf).status_code==409
    profile().subject_user_id='member-a';get_session().commit()
    assert consent(client,csrf).status_code==403
    assert get_session().query(VoiceConsent).count()==0 and voice.creates==0


def test_csrf_separate_consent_and_explicit_operator_are_required(voice,app,client,login):
    login();csrf=start(client)
    assert client.post('/f/a/person/pa/voice',data={'action':'consent'}).status_code==400
    assert consent(client,csrf).status_code==302
    assert client.get('/operations/voices').status_code==403
    assert review(app).status_code==302 and profile().status=='collecting'
    assert get_session().query(VoiceAudit).count()>=3


def test_personal_page_runs_the_shared_consent_upload_and_clone_flow(voice,app,client,login):
    login()
    path='/account/voices?family_id=a'
    body=client.get(path).get_data(as_text=True)
    assert '上传声音或录音克隆' in body and 'id="voice-sample-form"' not in body
    assert get_session().query(VoiceProfile).count()==0  # Merely opening the entry never creates a model.
    csrf=token(client,path);target='/f/a/person/pa/voice?from_account=1'
    response=client.post(target,data={'csrf_token':csrf,'action':'start'})
    assert response.status_code==302 and response.location.startswith('/account/voices?')
    assert 'person_id=pa' in response.location and 'family_id=a' in response.location
    assert client.post(target,data={'csrf_token':csrf,'action':'sample','quality':'yes'}).status_code==409
    assert voice.creates==0
    assert client.post(target,data=dict(csrf_token=csrf,action='consent',version=CONSENT_VERSION,adult='yes',agree='yes')).status_code==302
    assert 'id="voice-sample-form"' not in client.get(response.location).get_data(as_text=True)
    assert review(app).status_code==302
    body=client.get(response.location).get_data(as_text=True)
    assert 'id="voice-record"' in body and 'name="sample"' in body
    assert 'from_account=1' in body and 'aria-label="家庭导航"' in body
    uploaded=client.post(target,data=dict(csrf_token=csrf,action='sample',quality='yes',start='0',length='10',sample=(io.BytesIO(wav()),'mine.wav')))
    assert uploaded.status_code==302 and uploaded.location.startswith('/account/voices?')
    assert profile().status=='queued' and voice.creates==0
    with app.app_context():assert process_one()
    assert profile().status=='ready' and voice.creates==1
    body=client.get(uploaded.location).get_data(as_text=True)
    assert '已有声音档案' in body and 'id="voice-sample-form"' not in body


def test_personal_entry_does_not_grant_admin_the_right_to_clone_other_people(voice,app,client,login):
    login();csrf=token(client,'/account/voices?family_id=a')
    s=get_session();s.get(Person,'pa').user_id='member-a'
    s.get(Person,'pb').user_id='owner-a';s.get(Person,'pb').life_status='alive';s.commit()
    assert client.get('/account/voices?person_id=pa').status_code==404
    assert client.get('/account/voices?person_id=pb').status_code==404
    assert client.post('/f/a/person/pa/voice?from_account=1',data={'csrf_token':csrf,'action':'start'}).status_code==403
    assert get_session().query(VoiceProfile).count()==0 and voice.creates==0


def test_personal_entry_shows_feature_quota_and_unconfirmed_person_blockers(voice,app,client,login):
    login();app.config['VOICE_ENABLED']=False
    body=client.get('/account/voices?family_id=a').get_data(as_text=True)
    assert '声音克隆目前尚未开通' in body
    assert 'id="voice-record"' not in body and 'id="voice-sample-form"' not in body
    assert '开始建立声音档案' not in body
    app.config.update(VOICE_ENABLED=True,VOICE_FAMILY_LIMITS={})
    body=client.get('/account/voices?family_id=a').get_data(as_text=True)
    assert '尚无可用音色名额' in body and '开始建立声音档案' not in body
    app.config['VOICE_FAMILY_LIMITS']={'a':{'voices':2,'monthly_characters':50000}}
    s=get_session();s.get(Person,'pa').life_status='unknown';s.commit()
    body=client.get('/account/voices?family_id=a').get_data(as_text=True)
    assert '核实人物状态' in body and '开始建立声音档案' not in body


def test_personal_selector_is_explicit_across_families_and_never_lists_departed_people(voice,client,login):
    login();s=get_session()
    s.add(FamilyMember(id='my-second-family',family_id='b',user_id='owner-a',role='member'))
    s.get(Person,'pb').user_id='owner-a';s.get(Person,'pb').life_status='alive';s.commit()
    body=client.get('/account/voices').get_data(as_text=True)
    assert 'value="pa"' in body and 'value="pb"' in body
    assert '开始建立声音档案' not in body
    body=client.get('/account/voices?person_id=pb').get_data(as_text=True)
    assert 'href="/f/b/stories"' in body and 'href="/f/a/stories"' not in body
    s=get_session();s.query(FamilyMember).filter_by(id='my-second-family').one().del_flag=1;s.commit()
    assert client.get('/account/voices?person_id=pb').status_code==404
    assert 'Beta Person' not in client.get('/account/voices').get_data(as_text=True)


def test_repeated_story_play_uses_one_generation_and_no_arbitrary_text(voice,app,client,login):
    csrf=ready(app,client,login);response=request_audio(client,csrf);assert response.status_code==202
    assert request_audio(client,csrf).json['id']==response.json['id']
    assert get_session().query(VoiceCharge).count()==1
    with app.app_context():assert process_one()
    audio=client.get(response.json['status_url']).json;assert audio['status']=='ready'
    output=client.get(audio['audio_url']);assert output.status_code==200 and output.mimetype=='audio/wav'
    assert output.headers['Cache-Control']=='private, no-store' and 'AI 合成声音'.encode() in output.data
    assert request_audio(client,csrf).status_code==200 and voice.syntheses==1 and voice.creates==1
    assert request_audio(client,csrf,text='arbitrary').status_code==400
    body=client.get('/f/a/story/public-a').get_data(as_text=True)
    assert 'AI 合成声音' in body and profile().provider_voice_id not in body


def test_private_audio_follows_story_permissions_and_author_grant(voice,app,client,login):
    csrf=ready(app,client,login);response=request_audio(client,csrf,story='private-a');assert response.status_code==202
    with app.app_context():assert process_one()
    path=client.get(response.json['status_url']).json['audio_url']
    login('member-a');assert client.get(path).status_code==404
    csrf=token(client,'/account/privacy-requests')
    assert request_audio(client,csrf,story='private-a',authorize=False).status_code==404
    # A designated reader may read an unapproved story, but cannot send it to a provider.
    assert request_audio(client,csrf,story='specific-a',authorize=False).status_code==403
    assert request_audio(client,csrf,story='specific-a').status_code==403
    assert client.get('/f/b/person/pb/voice').status_code==404


def test_revision_invalidates_old_audio_and_requires_new_author_grant(voice,app,client,login):
    csrf=ready(app,client,login);response=request_audio(client,csrf)
    with app.app_context():process_one()
    old=client.get(response.json['status_url']).json['audio_url']
    s=get_session();s.query(Draft).filter_by(interview_id='public-a').one().content='Revised current version';s.commit()
    assert client.get(old).status_code==404
    assert request_audio(client,csrf,authorize=False).status_code==403
    assert request_audio(client,csrf).status_code==202
    with app.app_context():process_one()
    assert voice.syntheses==2


def test_deletion_revokes_immediately_and_confirms_remote_and_storage(voice,app,client,login):
    csrf=ready(app,client,login);response=request_audio(client,csrf)
    with app.app_context():process_one()
    url=client.get(response.json['status_url']).json['audio_url'];sample_key=profile().sample_key
    from pathlib import Path
    orphan=(Path(app.config['UPLOAD_DIR'])/sample_key).parent/'.private-interrupted'
    orphan.write_bytes(b'synthetic unfinished clip')
    voice.fail_delete=True
    assert client.post('/f/a/person/pa/voice',data=dict(csrf_token=csrf,action='delete')).status_code==302
    assert client.get(url).status_code==404
    with app.app_context():process_one()
    assert profile().status=='deleting' and voice.voices
    voice.fail_delete=False;profile().lease_until=None;get_session().commit()
    with app.app_context():process_one()
    assert profile().status=='deleted' and not voice.voices and profile().provider_voice_id is None
    assert not ( __import__('pathlib').Path(app.config['UPLOAD_DIR'])/sample_key).exists()
    assert not orphan.exists()
    assert get_session().query(VoiceAudio).one().storage_key is None
    assert get_session().query(VoiceConsent).one().revoked_at
    assert get_session().query(VoiceAudit).filter_by(action='reviewed').one().remarks=='evidence/synthetic-evidence-001'
    assert get_session().query(VoiceAudit).filter_by(action='provider_delete_ack').one().remarks=='receipt/synthetic-delete-receipt'


def test_delete_during_synthesis_discards_result_and_never_resurrects(voice,app,client,login):
    csrf=ready(app,client,login);response=request_audio(client,csrf)
    def withdraw():
        from voices import revoke
        revoke(profile(),'owner-a');get_session().commit()
    voice.on_synthesis=withdraw
    with app.app_context():process_one();process_one()
    assert profile().status=='deleted' and not voice.voices
    assert client.get(response.json['status_url']).status_code==404
    assert get_session().query(VoiceAudio).one().storage_key is None


def test_clone_timeout_is_not_retried_or_reported_as_deleted(voice,app,client,login):
    login();csrf=start(client);consent(client,csrf);review(app)
    client.post('/f/a/person/pa/voice',data=dict(csrf_token=csrf,action='sample',quality='yes',start='0',length='10',sample=(io.BytesIO(wav()),'clip.wav')))
    voice.on_create=lambda identifier:(_ for _ in ()).throw(VoiceError('provider_unavailable',True))
    with app.app_context():process_one();assert not process_one()
    assert profile().uncertain and voice.creates==1
    client.post('/f/a/person/pa/voice',data=dict(csrf_token=csrf,action='delete'))
    with app.app_context():process_one()
    assert profile().status=='deleting' and voice.voices


def test_quota_and_switch_off_do_not_block_deletion(voice,app,client,login):
    csrf=ready(app,client,login);app.config['VOICE_FAMILY_LIMITS']={'a':{'voices':2,'monthly_characters':0}}
    assert request_audio(client,csrf).status_code==403 and voice.syntheses==0
    app.config['VOICE_ENABLED']=False
    assert client.get('/f/a/person/pa/voice').status_code==200
    assert client.post('/f/a/person/pa/voice',data=dict(csrf_token=csrf,action='delete')).status_code==302
    with app.app_context():process_one()
    assert profile().status=='deleted'


def test_removed_member_or_relinked_subject_cannot_reuse_voice(voice,app,client,login):
    csrf=ready(app,client,login);response=request_audio(client,csrf)
    get_session().get(Person,'pa').user_id='member-a';get_session().commit()
    with app.app_context():process_one()
    assert voice.syntheses==0
    assert client.get(response.json['status_url']).status_code==404


def test_deceased_is_hidden_and_requires_two_relatives_plus_operator_review(voice,app,client,login):
    s=get_session();person=s.get(Person,'pa');person.life_status='deceased';person.user_id=None;s.commit()
    login();assert client.get('/f/a/person/pa/voice').status_code==404
    assert '管理声音与授权' not in client.get('/f/a/person/pa').get_data(as_text=True)
    app.config['VOICE_DECEASED_ENABLED']=True;csrf=start(client)
    data=dict(csrf_token=csrf,action='consent',version=CONSENT_VERSION,adult='yes',agree='yes',relation='成年子女',no_objection='yes')
    assert client.post('/f/a/person/pa/voice',data=data).status_code==302
    assert review(app).status_code==409
    login('member-a');data['csrf_token']=token(client,'/f/a/person/pa/voice')
    assert client.post('/f/a/person/pa/voice',data=data).status_code==302
    assert review(app).status_code==302 and profile().status=='collecting'


def test_private_audio_keys_never_get_photo_urls(voice,app,client,login):
    from storage import storage_url
    login();assert storage_url('voice/a/sensitive.wav')==''
    assert client.get('/uploads/voice/a/sensitive.wav').status_code==404


def test_real_adapter_uses_inline_sample_safe_errors_and_no_fake_outside_testing(app,monkeypatch):
    calls=[]
    class Response:
        status_code=200
        def json(self):return {'output':{'voice_id':'cosyvoice-v3.5-flash-test123-synthetic'}}
    def post(url,**kwargs):calls.append((url,kwargs));return Response()
    monkeypatch.setattr('voice_provider.requests.post',post)
    provider=CosyVoiceProvider('test-only-key','test-workspace')
    assert provider.create(wav(),'cosyvoice-v3.5-flash','test123').endswith('synthetic')
    assert calls[0][1]['json']['input']['audio'].startswith('data:audio/wav;base64,')
    assert calls[0][1]['allow_redirects'] is False
    app.config.update(TESTING=False,VOICE_COMPLIANCE_APPROVED=False,VOICE_TEST_PROVIDER=FakeProvider())
    with app.app_context(),pytest.raises(VoiceError,match='compliance_pending'):get_provider()


def test_sample_decoding_is_bounded_and_accepts_recorder_webm_without_duration(voice,app,tmp_path):
    import subprocess
    source=tmp_path/'source.wav';source.write_bytes(wav(12));output=tmp_path/'recording.webm'
    subprocess.run([app.config['VOICE_FFMPEG'],'-v','error','-i',str(source),'-c:a','libopus','-f','webm','-live','1',str(output)],check=True,capture_output=True)
    with app.app_context():
        normalized=voice_storage.normalize_sample(output.read_bytes(),1,10)
        with wave.open(io.BytesIO(normalized)) as result:assert result.getnframes()==240000
        with pytest.raises(VoiceError):voice_storage.normalize_sample(output.read_bytes(),0,61)
        with pytest.raises(VoiceError):voice_storage.normalize_sample(b'not audio',0,10)


def test_clone_completion_after_withdrawal_can_only_be_deleted(voice,app,client,login):
    login();csrf=start(client);consent(client,csrf);review(app)
    client.post('/f/a/person/pa/voice',data=dict(csrf_token=csrf,action='sample',quality='yes',start='0',length='10',sample=(io.BytesIO(wav()),'clip.wav')))
    def withdraw(identifier):
        from voices import revoke
        revoke(profile(),'owner-a');get_session().commit()
    voice.on_create=withdraw
    with app.app_context():process_one();process_one()
    assert profile().status=='deleted' and not voice.voices


def test_unknown_external_creation_is_reconciled_then_remote_resources_deleted(voice,app,client,login):
    login();csrf=start(client);consent(client,csrf);review(app)
    client.post('/f/a/person/pa/voice',data=dict(csrf_token=csrf,action='sample',quality='yes',start='0',length='10',sample=(io.BytesIO(wav()),'clip.wav')))
    voice.on_create=lambda identifier:(_ for _ in ()).throw(VoiceError('provider_unavailable',True))
    with app.app_context():process_one()
    operator=app.test_client()
    with operator.session_transaction() as state:state['user_id']='outsider'
    csrf=token(operator,'/operations/voices')
    assert operator.post('/operations/voices',data=dict(csrf_token=csrf,action='settled',profile_id=profile().id,worker_stopped='yes',provider_checked='yes',evidence_ref='actual-manual-check')).status_code==302
    with app.app_context():process_one()
    assert profile().status=='deleted' and not voice.voices and get_session().query(VoiceConsent).one().revoked_at


def test_paid_task_lease_is_claimed_once_and_expiry_never_retries_automatically(voice,app,client,login):
    from voice_worker import _claim
    from reporting import local_now
    csrf=ready(app,client,login);request_audio(client,csrf)
    with app.app_context():
        assert _claim(VoiceAudio,'queued')
        assert _claim(VoiceAudio,'queued') is None
        audio=get_session().query(VoiceAudio).one();audio.lease_until=local_now()-dt.timedelta(seconds=1);get_session().commit()
        assert not process_one()
    audio=get_session().query(VoiceAudio).one()
    assert audio.error_code=='external_unknown' and audio.lease_token and voice.syntheses==0
    assert request_audio(client,csrf,retry='yes').status_code==409


def test_audio_backup_rejects_missing_samples(voice,app,tmp_path):
    from sqlalchemy import create_engine,text
    from backup import _photo_keys,create_backup,BackupError
    path=tmp_path/'backup-source.db';url='sqlite:///'+str(path);engine=create_engine(url)
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE voice_profiles (sample_key TEXT)'))
        conn.execute(text("INSERT INTO voice_profiles VALUES ('voice/family/private.wav')"))
    assert _photo_keys(url)==['voice/family/private.wav']
    with pytest.raises(BackupError):create_backup(url,tmp_path/'backup.tar.gz',tmp_path/'empty-media')
    engine.dispose()


def test_author_can_withdraw_story_processing_without_deleting_the_family_voice(voice,app,client,login):
    csrf=ready(app,client,login);response=request_audio(client,csrf)
    with app.app_context():process_one()
    url=client.get(response.json['status_url']).json['audio_url']
    assert client.post('/f/a/story/public-a/voice/withdraw',data={'csrf_token':csrf}).status_code==302
    assert client.get(url).status_code==404
    with app.app_context():process_one()
    audio=get_session().query(VoiceAudio).one()
    assert audio.status=='purged' and audio.storage_key is None
    assert profile().status=='ready' and voice.voices and voice.syntheses==1


def test_real_provider_keeps_workspace_binding_and_allows_cleanup_after_switch_off(voice,app,client,login):
    ready(app,client,login)
    app.config.update(VOICE_TEST_PROVIDER=None,SECRET_KEY='strong-test-only-secret-more-than-32-characters',VOICE_COMPLIANCE_APPROVED=False,VOICE_API_KEY='not-a-real-key',VOICE_WORKSPACE_ID='another-workspace')
    with app.app_context():
        with pytest.raises(VoiceError,match='workspace_changed'):get_provider(cleanup=True,profile=profile())
        app.config['VOICE_WORKSPACE_ID']=profile().workspace_id='test-workspace'
        assert isinstance(get_provider(cleanup=True,profile=profile()),CosyVoiceProvider)
        with pytest.raises(VoiceError,match='compliance_pending'):get_provider(profile=profile())


def test_person_can_withdraw_own_consent_after_family_removal_and_switch_off(voice,app,client,login):
    ready(app,client,login);identifier=profile().id
    s=get_session();s.query(FamilyMember).filter_by(family_id='a',user_id='owner-a').one().del_flag=1;s.commit()
    app.config['VOICE_ENABLED']=False
    assert client.get('/f/a/person/pa/voice').status_code==404
    body=client.get('/account/voices').get_data(as_text=True)
    assert 'Alpha Person' not in body and 'Alpha Family' not in body and 'content-public-a' not in body
    csrf=re.search(r'name="csrf_token" value="([^"]+)"',body).group(1)
    assert client.post('/account/voices/'+identifier+'/withdraw',data={'csrf_token':csrf}).status_code==302
    with app.app_context():process_one()
    assert profile().status=='deleted'
    login('member-a');assert client.post('/account/voices/'+identifier+'/withdraw',data={'csrf_token':csrf}).status_code==400


@pytest.mark.parametrize('remove_family',[False,True])
def test_withdrawal_keeps_only_a_still_authorized_navigation_context(voice,app,client,login,remove_family):
    csrf=ready(app,client,login);identifier=profile().id
    page=client.get('/account/voices?family_id=a').get_data(as_text=True)
    assert 'aria-label="家庭导航"' in page
    assert 'href="/account?family_id=a"' in page
    assert '/account/voices/'+identifier+'/withdraw?family_id=a' in page
    if remove_family:
        s=get_session();s.query(FamilyMember).filter_by(family_id='a',user_id='owner-a').one().del_flag=1;s.commit()
    app.config['VOICE_ENABLED']=False
    response=client.post('/account/voices/'+identifier+'/withdraw?family_id=a',data={'csrf_token':csrf})
    assert response.status_code==302
    assert response.location==('/account/voices' if remove_family else '/account/voices?family_id=a')
    assert client.get(response.location).status_code==200
    assert profile().status=='deleting'


def test_deletion_always_targets_known_model_even_when_list_index_is_empty(voice,app,client,login):
    csrf=ready(app,client,login);assert voice.voices
    voice.list=lambda prefix:[]
    client.post('/f/a/person/pa/voice',data={'csrf_token':csrf,'action':'delete'})
    with app.app_context():process_one()
    assert profile().status=='deleted' and not voice.voices
