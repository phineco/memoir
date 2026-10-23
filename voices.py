"""Family-only voice lifecycle and versioned story audio. Provider work is never in HTTP requests."""
import datetime as dt
import hashlib
import io
import json
import re
import secrets

from flask import Blueprint,abort,current_app,redirect,render_template,request,send_file,url_for
from sqlalchemy import or_,func
from sqlalchemy.exc import IntegrityError

from access import family_role,story_visible
from forms import require_csrf
from models import (Draft,Family,Interview,Person,User,VoiceAudio,VoiceAudit,VoiceCharge,
                    VoiceConsent,VoiceProfile,get_session,new_id)
from operations import require_operator
from reporting import local_now
from search_index import plain_text
from voice_provider import VoiceError,get_provider
import voice_storage
from views import _current_user,_family_or_404,_person_or_404,_can_edit_story

bp=Blueprint('voices',__name__)
CONSENT_VERSION='2026-10-23.1'
STATES={'consent':'待单独同意','review':'待运营核验','collecting':'可采集样本','queued':'处理中','processing':'处理中',
        'ready':'可用','failed':'未完成，请查看说明','disabled':'已停用','deleting':'删除处理中','deleted':'已删除'}
RELATIONS=('配偶','成年子女','父母','其他近亲属')


def enabled():return bool(current_app.config.get('VOICE_ENABLED'))


@bp.before_request
def guard():
    if request.method=='POST':request.max_content_length=11*1024*1024 if request.endpoint=='voices.manage' else 16384
    # Turning the switch off stops new usage, but must never prevent withdrawal/deletion or cleanup.
    cleanup=request.method=='POST' and ((request.endpoint in ('voices.manage','voices.operations') and request.form.get('action') in ('delete','withdraw','disable','settled')) or request.endpoint in ('voices.withdraw_story','voices.withdraw_own'))
    inspection=request.method=='GET' and request.endpoint in ('voices.manage','voices.operations','voices.my_voices')
    if not enabled() and not cleanup and not inspection:abort(404)
    if enabled() and not current_app.testing and len(current_app.secret_key or '')<32:abort(503,'声音功能尚未安全配置，请联系运营')
    if not _current_user():abort(401)


def audit(profile,action,actor=None,receipt=None,reference=None):
    note=None
    if isinstance(reference,str) and re.fullmatch(r'[A-Za-z0-9._-]{1,80}',reference):note='evidence/'+reference
    elif isinstance(receipt,str) and re.fullmatch(r'[A-Za-z0-9_-]{1,128}',receipt):note='receipt/'+receipt
    get_session().add(VoiceAudit(id=new_id(),profile_id=profile.id,epoch=profile.epoch,action=action,
                               create_by=actor,create_date=local_now(),remarks=note))


def limits(family_id):
    try:
        config=current_app.config['VOICE_FAMILY_LIMITS']
        values=(json.loads(config) if isinstance(config,str) else config).get(family_id,{})
        count=values.get('voices',0);chars=values.get('monthly_characters',0)
        if type(count) is not int or type(chars) is not int or not 0<=count<=20 or not 0<=chars<=10000000:raise ValueError
        return count,chars
    except (ValueError,TypeError,AttributeError):return 0,0


def consents_valid(profile):
    s=get_session();person=s.query(Person).filter_by(id=profile.person_id,family_id=profile.family_id,del_flag=0).first()
    if not person or person.life_state!=profile.subject_state or person.user_id!=profile.subject_user_id:return False
    rows=s.query(VoiceConsent).filter_by(profile_id=profile.id,epoch=profile.epoch,version=CONSENT_VERSION,revoked_at=None,del_flag=0).all()
    valid=[row for row in rows if s.query(User.id).filter_by(id=row.user_id,del_flag=0).first() and family_role(s,profile.family_id,row.user_id)]
    if person.life_state=='alive':return any(row.user_id==person.user_id and row.relation=='本人' for row in valid)
    return bool(current_app.config.get('VOICE_DECEASED_ENABLED') and len({row.user_id for row in valid if row.relation in RELATIONS})>=2)


def permitted(profile):
    return bool(profile and profile.del_flag==0 and profile.reviewed_at and consents_valid(profile))


def manager(family_id,person,user):
    return user and (person.user_id==user.id or family_role(get_session(),family_id,user.id) in ('owner','admin'))


def story_content(story):
    draft=get_session().query(Draft).filter_by(interview_id=story.id,is_current=True,del_flag=0).order_by(Draft.version.desc(),Draft.id).first()
    if not draft:raise VoiceError('no_content')
    text=((story.topic or '')+'\n'+plain_text(draft.content)).strip()
    if not text or len(text)>20000:raise VoiceError('text_limit')
    digest=hashlib.sha256((draft.id+'\0'+text).encode()).hexdigest()
    return draft,text,digest


def story_granted(story,draft,digest):
    if draft.voice_authorized_hash!=digest:return False
    s=get_session();actor=s.query(User).filter_by(id=draft.voice_authorized_by,del_flag=0).first()
    if not actor:return False
    if story.author_id:return actor.id==story.author_id
    return (story.visibility or 'public')=='public' and family_role(s,story.family_id,actor.id) in ('owner','admin')


def story_context(story,user):
    if not enabled():return {}
    try:draft,text,digest=story_content(story)
    except VoiceError:return {}
    profiles=get_session().query(VoiceProfile).filter_by(family_id=story.family_id,status='ready',del_flag=0).all()
    profiles=[row for row in profiles if permitted(row)]
    people={row.id:row.name for row in get_session().query(Person).filter_by(family_id=story.family_id,del_flag=0)}
    fam=get_session().query(Family).filter_by(id=story.family_id).one()
    return dict(voice_profiles=profiles,voice_names=people,voice_stamp=digest,
                voice_authorized=story_granted(story,draft,digest),
                voice_can_authorize=_can_edit_story(story,user,fam))


def person_context(person,user):
    if not enabled() or person.life_state=='deceased':return {}
    profile=get_session().query(VoiceProfile).filter_by(person_id=person.id,family_id=person.family_id).first()
    return dict(person_voice=profile,voice_manager=manager(person.family_id,person,user),voice_states=STATES)


def revoke(profile,actor):
    profile.status='deleting';profile.error_code=None
    s=get_session();now=local_now()
    s.query(VoiceConsent).filter_by(profile_id=profile.id,epoch=profile.epoch,revoked_at=None).update({VoiceConsent.revoked_at:now},synchronize_session=False)
    s.query(VoiceAudio).filter_by(profile_id=profile.id).update({VoiceAudio.status:'revoked'},synchronize_session=False)
    audit(profile,'delete_requested',actor)


@bp.get('/account/voices')
def my_voices():
    me=_current_user();s=get_session()
    rows=s.query(VoiceProfile,VoiceConsent).join(VoiceConsent,VoiceConsent.profile_id==VoiceProfile.id).filter(
        VoiceConsent.user_id==me.id,VoiceConsent.epoch==VoiceProfile.epoch).order_by(VoiceConsent.create_date.desc(),VoiceProfile.id).all()
    return render_template('my_voices.html',rows=rows,states=STATES)


@bp.post('/account/voices/<profile_id>/withdraw')
def withdraw_own(profile_id):
    require_csrf();me=_current_user();s=get_session()
    profile=s.query(VoiceProfile).filter_by(id=profile_id).with_for_update().first()
    if not profile or not s.query(VoiceConsent.id).filter_by(profile_id=profile_id,epoch=profile.epoch,user_id=me.id,revoked_at=None).first():abort(404)
    if profile.status!='deleted':revoke(profile,me.id)
    s.commit();return redirect(url_for('voices.my_voices'))


@bp.route('/f/<family_id>/person/<person_id>/voice',methods=['GET','POST'])
def manage(family_id,person_id):
    fam=_family_or_404(family_id);person=_person_or_404(family_id,person_id);me=_current_user();s=get_session()
    profile=s.query(VoiceProfile).filter_by(person_id=person_id,family_id=family_id).first()
    if not enabled() and not profile:abort(404)
    own_consent=bool(profile and s.query(VoiceConsent.id).filter_by(profile_id=profile.id,epoch=profile.epoch,user_id=me.id,revoked_at=None).first())
    can_manage=manager(family_id,person,me)
    if not can_manage and not own_consent and person.life_state!='deceased':abort(403)
    if person.life_state=='deceased' and not current_app.config.get('VOICE_DECEASED_ENABLED'):
        cleanup=profile and (can_manage or own_consent) and (request.method=='GET' or request.form.get('action') in ('delete','withdraw','disable'))
        if not cleanup:abort(404)
    if request.method=='POST':
        require_csrf();action=request.form.get('action')
        s.rollback();s.query(Family).filter_by(id=family_id).with_for_update().one()
        profile=s.query(VoiceProfile).filter_by(person_id=person_id,family_id=family_id).with_for_update().populate_existing().first()
        if action=='start':
            if not can_manage:abort(403)
            if person.life_state not in ('alive','deceased'):abort(400,'请先核实人物生存状态')
            if person.life_state=='alive' and not person.user_id:abort(400,'须先关联本人的账号，再由本人单独同意')
            if profile and profile.status!='deleted':abort(409)
            quota,_=limits(family_id)
            used=s.query(VoiceProfile.id).filter(VoiceProfile.family_id==family_id,VoiceProfile.status!='deleted').count()
            if used>=quota:abort(403,'此家庭尚无可用音色名额，请联系运营核对开通额度')
            if not profile:
                profile=VoiceProfile(id=new_id(),person_id=person_id,family_id=family_id,epoch=1,model=current_app.config['VOICE_MODEL'],workspace_id=current_app.config['VOICE_WORKSPACE_ID'],prefix=secrets.token_hex(5),subject_state=person.life_state,subject_user_id=person.user_id,create_by=me.id,create_date=local_now())
                s.add(profile)
            else:
                profile.epoch+=1;profile.prefix=secrets.token_hex(5);profile.status='consent';profile.model=current_app.config['VOICE_MODEL']
                profile.workspace_id=current_app.config['VOICE_WORKSPACE_ID']
                profile.subject_state=person.life_state;profile.subject_user_id=person.user_id;profile.reviewed_at=None;profile.reviewed_by=None;profile.evidence_ref=None;profile.uncertain=False;profile.error_code=None
            audit(profile,'started',me.id)
        elif not profile:abort(404)
        elif action=='consent':
            if profile.status not in ('consent','review'):abort(409)
            if request.form.get('version')!=CONSENT_VERSION or request.form.get('agree')!='yes' or request.form.get('adult')!='yes':abort(400,'须本人阅读并单独确认，且仅限成年人')
            if profile.subject_state!=person.life_state or profile.subject_user_id!=person.user_id:abort(409)
            if person.life_state=='alive':
                if person.user_id!=me.id:abort(403)
                relation='本人'
            else:
                relation=request.form.get('relation')
                if relation not in RELATIONS or request.form.get('no_objection')!='yes':abort(400)
            existing=s.query(VoiceConsent.id).filter_by(profile_id=profile.id,epoch=profile.epoch,user_id=me.id).first()
            if not existing:s.add(VoiceConsent(id=new_id(),profile_id=profile.id,epoch=profile.epoch,user_id=me.id,relation=relation,version=CONSENT_VERSION,create_by=me.id,create_date=local_now()))
            profile.status='review';profile.reviewed_at=None;audit(profile,'consented',me.id)
        elif action in ('delete','withdraw','disable'):
            own=s.query(VoiceConsent.id).filter_by(profile_id=profile.id,epoch=profile.epoch,user_id=me.id,revoked_at=None).first()
            if not can_manage and not own:abort(403)
            if action=='disable':
                if profile.status in ('deleting','deleted'):abort(409)
                profile.status='disabled';audit(profile,'disabled',me.id)
            elif profile.status!='deleted':revoke(profile,me.id)
        elif action=='resume':
            if not can_manage or profile.status!='disabled' or not permitted(profile) or not profile.provider_voice_id:abort(409)
            profile.status='queued';profile.lease_until=None;audit(profile,'resume_requested',me.id)
        elif action=='sample':
            if not can_manage:abort(403)
            if profile.status not in ('collecting','failed') or not permitted(profile) or profile.uncertain or profile.provider_voice_id or profile.lease_token:abort(409,'请先完成单独同意和运营核验，或等待原任务处理')
            if request.form.get('quality')!='yes':abort(400,'请先试听并确认样本仅有已授权的本人声音')
            try:start=float(request.form.get('start','0'));length=float(request.form.get('length','20'))
            except ValueError:abort(400)
            upload=request.files.get('sample')
            if not upload:abort(400)
            # Only a normalized selected clip is retained. Original file lives in private temp storage.
            data=voice_storage.normalize_sample(upload.read(10*1024*1024+1),start,length)
            key=f'voice/{family_id}/{profile.id}/{profile.epoch}/sample.wav'
            voice_storage.save(data,key);profile.sample_key=key;profile.status='queued';profile.error_code=None;profile.lease_until=None
            audit(profile,'sample_submitted',me.id)
        else:abort(400)
        s.commit();return redirect(url_for('voices.manage',family_id=family_id,person_id=person_id))
    consents=s.query(VoiceConsent).filter_by(profile_id=profile.id,epoch=profile.epoch).all() if profile else []
    return render_template('voice_manage.html',family=fam,person=person,profile=profile,states=STATES,consents=consents,
                           can_manage=can_manage,consent_version=CONSENT_VERSION,relations=RELATIONS,voice_enabled=enabled(),
                           can_sample=bool(profile and permitted(profile) and profile.status in ('collecting','failed') and not profile.uncertain and not profile.provider_voice_id))


@bp.errorhandler(VoiceError)
def voice_error(error):
    return {'ok':False,'error':'声音服务暂不可用；请核对样本，或使用普通朗读。','code':error.code},503


@bp.route('/f/<family_id>/person/<person_id>/voice/sample')
def sample(family_id,person_id):
    _family_or_404(family_id);person=_person_or_404(family_id,person_id)
    if not manager(family_id,person,_current_user()):abort(403)
    profile=get_session().query(VoiceProfile).filter_by(person_id=person_id,family_id=family_id).first()
    if not profile or not permitted(profile) or profile.status in ('deleting','deleted','disabled'):abort(404)
    return private_audio(voice_storage.read(profile.sample_key,4*1024*1024))


@bp.route('/f/<family_id>/person/<person_id>/voice/permission')
def sample_permission(family_id,person_id):
    _family_or_404(family_id);person=_person_or_404(family_id,person_id)
    if not manager(family_id,person,_current_user()):abort(403)
    profile=get_session().query(VoiceProfile).filter_by(person_id=person_id,family_id=family_id).first()
    if not permitted(profile) or profile.status not in ('collecting','failed') or profile.uncertain or profile.provider_voice_id or profile.lease_token:abort(409)
    return {'ok':True}


def private_audio(data):
    response=send_file(io.BytesIO(data),mimetype='audio/wav',conditional=False,etag=False)
    response.headers.update({'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})
    return response


def _story(family_id,story_id):
    fam=_family_or_404(family_id);s=get_session();me=_current_user()
    story=s.query(Interview).filter_by(id=story_id,family_id=family_id,del_flag=0).first()
    if not story or not story_visible(s,story,me.id):abort(404)
    return fam,story,me


@bp.route('/f/<family_id>/story/<story_id>/voice',methods=['POST'])
def request_audio(family_id,story_id):
    fam,story,me=_story(family_id,story_id);require_csrf();s=get_session()
    data=request.get_json(silent=True)
    if not isinstance(data,dict) or set(data)-{'profile_id','stamp','authorize','retry'}:abort(400)
    s.rollback();s.query(Family).filter_by(id=family_id).with_for_update().one()
    profile=s.query(VoiceProfile).filter_by(id=data.get('profile_id'),family_id=family_id,status='ready',del_flag=0).with_for_update().first()
    if not permitted(profile):abort(404)
    draft,text,digest=story_content(story)
    if data.get('stamp')!=digest:abort(409,'文章已修订，请刷新后重新核对朗读范围')
    if data.get('authorize')=='yes':
        if not _can_edit_story(story,me,fam):abort(403)
        if not story_granted(story,draft,digest):
            draft.voice_authorized_hash=digest;draft.voice_authorized_at=local_now();draft.voice_authorized_by=me.id
            audit(profile,'story_authorized',me.id,reference=digest)
    if not story_granted(story,draft,digest):abort(403,'须作者先同意将本版本正文交给语音服务朗读')
    identifier=hashlib.sha256((profile.id+'\0'+str(profile.epoch)+'\0'+profile.model+'\0'+digest).encode()).hexdigest()
    audio=s.query(VoiceAudio).filter_by(id=identifier).with_for_update().first()
    if audio and audio.status in ('ready','queued','processing'):
        s.commit();return audio_result(audio),200
    if audio and (data.get('retry')!='yes' or audio.error_code=='external_unknown' or audio.lease_token):abort(409,'原任务未完成，请核对后明确重试；费用状态未知时由运营处理')
    _,budget=limits(family_id);period=local_now().strftime('%Y-%m')
    reserved=s.query(func.coalesce(func.sum(VoiceCharge.characters),0)).filter_by(family_id=family_id,period=period).scalar()
    if reserved+len(text)>budget:abort(403,'本月语音额度不足，可继续使用普通朗读')
    if audio and audio.update_date and audio.update_date>local_now()-dt.timedelta(seconds=30):abort(429)
    if not audio:
        audio=VoiceAudio(id=identifier,family_id=family_id,profile_id=profile.id,epoch=profile.epoch,interview_id=story.id,draft_id=draft.id,text_hash=digest,requested_by=me.id,create_by=me.id,create_date=local_now());s.add(audio)
    charge=VoiceCharge(id=new_id(),family_id=family_id,audio_id=identifier,period=period,characters=len(text),create_by=me.id,create_date=local_now());s.add(charge)
    audio.charge_id=charge.id;audio.requested_by=me.id;audio.status='queued';audio.error_code=None;audio.lease_until=None;audio.update_date=local_now()
    s.commit();return audio_result(audio),202


def audio_result(audio):
    return {'ok':True,'id':audio.id,'status':audio.status,'status_url':url_for('voices.audio_status',family_id=audio.family_id,story_id=audio.interview_id,audio_id=audio.id),
            'audio_url':url_for('voices.audio_bytes',family_id=audio.family_id,story_id=audio.interview_id,audio_id=audio.id) if audio.status=='ready' else None}


def checked_audio(family_id,story_id,audio_id):
    _,story,_=_story(family_id,story_id);s=get_session()
    audio=s.query(VoiceAudio).filter_by(id=audio_id,family_id=family_id,interview_id=story_id,del_flag=0).first()
    if not audio:abort(404)
    profile=s.query(VoiceProfile).filter_by(id=audio.profile_id,status='ready',epoch=audio.epoch,del_flag=0).first()
    if not permitted(profile):abort(404)
    draft,_,digest=story_content(story)
    if audio.draft_id!=draft.id or audio.text_hash!=digest or not story_granted(story,draft,digest):abort(404)
    return audio


@bp.route('/f/<family_id>/story/<story_id>/voice/withdraw',methods=['POST'])
def withdraw_story(family_id,story_id):
    fam,story,me=_story(family_id,story_id);require_csrf()
    if not _can_edit_story(story,me,fam):abort(403)
    s=get_session();s.rollback();s.query(Family).filter_by(id=family_id).with_for_update().one()
    draft,_,digest=story_content(story);draft.voice_authorized_hash=None
    profiles=set()
    for audio in s.query(VoiceAudio).filter_by(interview_id=story_id,family_id=family_id).all():
        audio.status='revoked';profiles.add(audio.profile_id)
    for identifier in profiles:
        profile=s.get(VoiceProfile,identifier)
        if profile:audit(profile,'story_grant_revoked',me.id,reference=digest)
    s.commit();return redirect(url_for('main.story_detail',family_id=family_id,interview_id=story_id))


@bp.route('/f/<family_id>/story/<story_id>/voice/<audio_id>')
def audio_status(family_id,story_id,audio_id):return audio_result(checked_audio(family_id,story_id,audio_id))


@bp.route('/f/<family_id>/story/<story_id>/voice/<audio_id>/audio')
def audio_bytes(family_id,story_id,audio_id):
    audio=checked_audio(family_id,story_id,audio_id)
    if audio.status!='ready':abort(404)
    return private_audio(voice_storage.read(audio.storage_key))


@bp.route('/operations/voices',methods=['GET','POST'])
def operations():
    me=_current_user();require_operator(me);s=get_session()
    if request.method=='POST':
        require_csrf();profile=s.query(VoiceProfile).filter_by(id=request.form.get('profile_id')).with_for_update().first()
        if not profile:abort(404)
        action=request.form.get('action')
        if action=='delete':revoke(profile,me.id)
        elif action=='settled':
            if request.form.get('worker_stopped')!='yes' or request.form.get('provider_checked')!='yes' or not re.fullmatch(r'[A-Za-z0-9._-]{1,80}',request.form.get('evidence_ref','')):abort(400)
            if profile.status not in ('deleting','failed'):abort(409)
            revoke(profile,me.id)
            # Explicit human confirmation only after worker termination and provider reconciliation.
            profile.uncertain=False;profile.lease_token=None;profile.lease_until=None
            if request.form.get('known_deleted')=='yes':profile.provider_voice_id=None
            profile.evidence_ref=request.form['evidence_ref']
            s.query(VoiceAudio).filter_by(profile_id=profile.id).update({VoiceAudio.lease_token:None,VoiceAudio.lease_until:None},synchronize_session=False)
            audit(profile,'external_settled',me.id,reference=profile.evidence_ref)
        elif action=='review':
            if profile.status not in ('review','consent') or not consents_valid(profile):abort(409)
            if not all(request.form.get(key)=='yes' for key in ('identity_verified','provider_authorized','scope_verified')):abort(400)
            ref=request.form.get('evidence_ref','')
            if not re.fullmatch(r'[A-Za-z0-9._-]{1,80}',ref):abort(400)
            profile.reviewed_by=me.id;profile.reviewed_at=local_now();profile.evidence_ref=ref;profile.status='collecting';audit(profile,'reviewed',me.id,reference=ref)
        else:abort(400)
        s.commit();return redirect(url_for('voices.operations'))
    try:page=int(request.args.get('page','1'))
    except ValueError:abort(400)
    if page<1:abort(400)
    total=s.query(VoiceProfile).count();pages=max(1,(total+19)//20);page=min(page,pages)
    rows=s.query(VoiceProfile).order_by(VoiceProfile.create_date,VoiceProfile.id).limit(20).offset((page-1)*20).all()
    groups={row.id:s.query(VoiceConsent).filter_by(profile_id=row.id,epoch=row.epoch).order_by(VoiceConsent.create_date,VoiceConsent.id).all() for row in rows}
    return render_template('voice_operations.html',profiles=rows,states=STATES,consent_groups=groups,page=page,pages=pages)
