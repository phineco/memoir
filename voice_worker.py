"""One bounded queue step. CAS leases prevent parallel workers from repeating paid operations."""
import datetime as dt
import secrets

from flask import current_app
from sqlalchemy import or_

from access import story_visible
from models import Interview,User,VoiceAudio,VoiceCharge,VoiceProfile,get_session
from reporting import local_now
from voice_provider import VoiceError,get_provider
import voice_storage
from voices import audit,enabled,permitted,story_content,story_granted


def _claim(model,status):
    s=get_session();now=local_now()
    candidates=s.query(model.id).filter(model.status==status,model.lease_token.is_(None),
        or_(model.lease_until.is_(None),model.lease_until<now)).order_by(model.create_date,model.id).limit(10).all()
    for row in candidates:
        token=secrets.token_hex(16)
        claimed=s.query(model).filter_by(id=row.id,status=status,lease_token=None).filter(
            or_(model.lease_until.is_(None),model.lease_until<now)).update({model.lease_token:token,
            model.lease_until:now+dt.timedelta(minutes=10),model.status:'processing' if status=='queued' else status},synchronize_session=False)
        s.commit()
        if claimed:return row.id,token
    return None


def _live(row,token):return row.lease_token==token and row.lease_until and row.lease_until>=local_now()


def _release(row,token,delay=0):
    if row.lease_token==token:
        row.lease_token=None;row.lease_until=local_now()+dt.timedelta(seconds=delay) if delay else None


def _profile_job(identifier,token,deleting):
    s=get_session();profile=s.get(VoiceProfile,identifier);provider=None
    try:
        if deleting:
            if profile.uncertain:raise VoiceError('external_unknown',True)
            if s.query(VoiceAudio.id).filter(VoiceAudio.profile_id==identifier,VoiceAudio.lease_token.isnot(None)).first():
                raise VoiceError('jobs_pending')
            # Resolve even IDs lost between create response and DB commit by the unique provider prefix.
            if profile.provider_voice_id or profile.sample_key:
                provider=get_provider(cleanup=True,profile=profile)
                targets=set(provider.list(profile.prefix))
                if profile.provider_voice_id:targets.add(profile.provider_voice_id)
                for voice in sorted(targets):
                    receipt=provider.delete(voice)
                    if receipt:audit(profile,'provider_delete_ack',receipt=receipt)
                    if profile.provider_voice_id==voice:profile.provider_voice_id=None
                    s.commit()
                if provider.list(profile.prefix):raise VoiceError('delete_pending')
            for audio in s.query(VoiceAudio).filter_by(profile_id=identifier).all():
                voice_storage.delete(audio.storage_key or f'voice/{audio.family_id}/{audio.profile_id}/{audio.epoch}/{audio.id}.wav');audio.storage_key=None;audio.status='revoked'
            voice_storage.delete(profile.sample_key or f'voice/{profile.family_id}/{profile.id}/{profile.epoch}/sample.wav')
            voice_storage.purge_local_profile(profile.family_id,profile.id)
            s.expire(profile)
            if not _live(profile,token) or profile.status!='deleting':raise VoiceError('lease_changed',True)
            profile.sample_key=None;profile.provider_voice_id=None;profile.status='deleted';profile.error_code=None
            profile.reviewed_at=None;profile.evidence_ref=None;audit(profile,'deleted')
        else:
            if not enabled() or not permitted(profile) or profile.status!='processing':raise VoiceError('authorization_changed')
            provider=get_provider(profile=profile)
            if not profile.provider_voice_id:
                sample=voice_storage.read(profile.sample_key,4*1024*1024)
                identifier_remote=provider.create(sample,profile.model,profile.prefix)
                s.expire(profile)
                if profile.lease_token!=token:raise VoiceError('lease_changed',True)
                profile.provider_voice_id=identifier_remote;s.commit()
            s.expire(profile)
            if not _live(profile,token):raise VoiceError('lease_changed',True)
            if profile.status!='processing' or not permitted(profile):raise VoiceError('authorization_changed')
            status,model=provider.query(profile.provider_voice_id)
            s.expire(profile)
            if not _live(profile,token):raise VoiceError('lease_changed',True)
            if profile.status=='processing' and permitted(profile):
                if model!=profile.model:raise VoiceError('model_mismatch')
                profile.status={'OK':'ready','DEPLOYING':'queued','UNDEPLOYED':'failed'}[status]
                profile.error_code=None if status=='OK' else 'provider_review' if status=='UNDEPLOYED' else None
                audit(profile,'clone_'+profile.status)
        _release(profile,token,30 if profile.status=='queued' else 0);s.commit()
    except Exception as error:
        s.rollback();profile=s.query(VoiceProfile).filter_by(id=identifier).populate_existing().one()
        if profile.lease_token==token:
            code=error.code if isinstance(error,VoiceError) else 'operation_failed'
            uncertain=error.uncertain if isinstance(error,VoiceError) else True
            profile.uncertain=profile.uncertain or uncertain;profile.error_code=code
            if profile.status=='processing':profile.status='failed'
            _release(profile,token,60 if deleting and profile.status=='deleting' else 0);audit(profile,'operation_failed');s.commit()
        # Log only event category and row id, never exception text/provider response/sample.
        current_app.logger.warning('voice operation did not complete')


def _audio_job(identifier,token):
    s=get_session();audio=s.get(VoiceAudio,identifier);key=f'voice/{audio.family_id}/{audio.profile_id}/{audio.epoch}/{audio.id}.wav'
    try:
        profile=s.get(VoiceProfile,audio.profile_id);story=s.get(Interview,audio.interview_id)
        def valid():
            user=s.query(User.id).filter_by(id=audio.requested_by,del_flag=0).first()
            return bool(enabled() and user and profile.status=='ready' and profile.epoch==audio.epoch and permitted(profile)
                        and story and story_visible(s,story,audio.requested_by))
        if not valid():raise VoiceError('authorization_changed')
        draft,text,digest=story_content(story)
        if audio.draft_id!=draft.id or audio.text_hash!=digest or not story_granted(story,draft,digest):raise VoiceError('version_changed')
        audio.storage_key=key;s.commit()
        data=get_provider(profile=profile).synthesize(profile.provider_voice_id,profile.model,text)
        data=voice_storage.label_audio(data,audio.id)
        s.expire_all()
        if not valid() or audio.status!='processing' or not _live(audio,token):raise VoiceError('authorization_changed')
        current_draft,_,current_hash=story_content(story)
        if current_draft.id!=draft.id or current_hash!=digest or not story_granted(story,current_draft,digest):raise VoiceError('version_changed')
        voice_storage.save(data,key)
        s.expire_all()
        # Profile lock serializes publication with deletion/disable; external work never holds it.
        profile=s.query(VoiceProfile).filter_by(id=profile.id).with_for_update().populate_existing().one()
        if not valid() or audio.status!='processing' or not _live(audio,token):raise VoiceError('authorization_changed')
        final_draft,_,final_hash=story_content(story)
        if final_draft.id!=audio.draft_id or final_hash!=audio.text_hash or not story_granted(story,final_draft,final_hash):raise VoiceError('version_changed')
        audio.status='ready';audio.error_code=None
        charge=s.get(VoiceCharge,audio.charge_id);charge.status='completed'
        _release(audio,token);s.commit()
    except Exception as error:
        s.rollback()
        cleaned=False
        try:voice_storage.delete(key);cleaned=True
        except Exception:pass
        audio=s.query(VoiceAudio).filter_by(id=identifier).populate_existing().one()
        if audio.lease_token==token:
            audio.error_code='external_unknown' if not isinstance(error,VoiceError) or error.uncertain else error.code
            if audio.status=='processing':audio.status='failed'
            if cleaned:audio.storage_key=None;_release(audio,token)
            charge=s.get(VoiceCharge,audio.charge_id)
            if charge:charge.status='uncertain' if audio.error_code=='external_unknown' else 'not_completed'
            s.commit()
        current_app.logger.warning('voice audio did not complete')


def process_one():
    s=get_session();now=local_now()
    # Expiry is not proof a paid request never reached the provider. Require explicit reconciliation.
    for model in (VoiceProfile,VoiceAudio):
        for row in s.query(model).filter(model.lease_token.isnot(None),model.lease_until<now).limit(100).all():
            row.error_code='external_unknown'
            if row.status=='processing':row.status='failed'
            if model is VoiceProfile:row.uncertain=True
            else:
                charge=s.get(VoiceCharge,row.charge_id)
                if charge:charge.status='uncertain'
    s.commit()
    job=_claim(VoiceProfile,'deleting')
    if job:_profile_job(*job,deleting=True);return True
    job=_claim(VoiceAudio,'revoked')
    if job:
        identifier,token=job;audio=s.get(VoiceAudio,identifier)
        try:
            voice_storage.delete(audio.storage_key or f'voice/{audio.family_id}/{audio.profile_id}/{audio.epoch}/{audio.id}.wav')
            audio.storage_key=None;audio.status='purged';_release(audio,token);s.commit()
        except Exception:
            s.rollback();audio=s.get(VoiceAudio,identifier);_release(audio,token,60);audio.error_code='storage_delete';s.commit()
        return True
    if not enabled():return False
    job=_claim(VoiceProfile,'queued')
    if job:_profile_job(*job,deleting=False);return True
    job=_claim(VoiceAudio,'queued')
    if job:_audio_job(*job);return True
    return False
