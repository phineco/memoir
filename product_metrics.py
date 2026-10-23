"""Restricted weekly product measures; client samples and manual evidence stay distinct."""
import datetime as dt
import hashlib
import re
import secrets

from flask import Blueprint,abort,current_app,redirect,render_template,request,url_for
from sqlalchemy.exc import IntegrityError

from access import family_role
from forms import require_csrf
from models import (AiTurn,Family,FamilyVisit,Interview,MetricSample,StoryCorrection,StoryPublication,
                    UsageEvent,User,VerificationItem,get_session)
from operations import require_operator
from reporting import current_period,local_now,report_period
from views import _current_user,_family_or_404


bp=Blueprint('metrics',__name__)
TASKS={'login':'登录','read':'阅读故事','large_text':'调大字号','stop_read':'停止朗读','dictation':'输入回忆','draft_recovery':'恢复草稿'}


def collection_enabled():
    operators=current_app.config.get('OPERATIONS_USER_IDS',())
    return bool(current_app.config.get('USAGE_METRICS_ENABLED') and operators and
                get_session().query(User.id).filter(User.id.in_(operators),User.del_flag==0).first())


@bp.route('/f/<family_id>/usage',methods=['POST'])
def collect(family_id):
    me=_current_user()
    if not me:abort(401)
    _family_or_404(family_id)
    if not collection_enabled():abort(404)
    if request.content_length and request.content_length>16384:abort(413)
    require_csrf()
    data=request.get_json(silent=True)
    if not isinstance(data,dict) or set(data)-{'user_id','events'}:abort(400)
    if data.get('user_id')!=me.id:abort(409)
    events=data.get('events')
    if not isinstance(events,list) or not 1<=len(events)<=20:abort(400)
    prepared={}
    for item in events:
        if not isinstance(item,dict) or set(item)!={'id','kind','outcome','duration_ms'}:abort(400)
        if not isinstance(item['id'],str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,80}',item['id']):abort(400)
        if item['kind'] not in ('retention','restore') or item['outcome'] not in ('success','failed'):abort(400)
        if type(item['duration_ms']) is not int or not 0<=item['duration_ms']<=60000:abort(400)
        identifier=hashlib.sha256((me.id+'\0'+family_id+'\0'+item['id']).encode()).hexdigest()
        values={key:item[key] for key in ('kind','outcome','duration_ms')}
        if identifier in prepared and prepared[identifier]!=values:abort(409)
        prepared[identifier]=values
    s=get_session()
    s.query(User).filter_by(id=me.id,del_flag=0).with_for_update().one()
    existing={row.id:row for row in s.query(UsageEvent).filter(UsageEvent.id.in_(prepared)).with_for_update().all()}
    for identifier,row in existing.items():
        if any(getattr(row,key)!=value for key,value in prepared[identifier].items()):abort(409)
    new={key:value for key,value in prepared.items() if key not in existing}
    recent=s.query(UsageEvent.id).filter(UsageEvent.user_id==me.id,UsageEvent.family_id==family_id,
        UsageEvent.create_date>=local_now()-dt.timedelta(hours=1)).with_for_update().limit(1001).all()
    if len(recent)+len(new)>1000:abort(429)
    now=local_now()
    for identifier,values in new.items():
        s.add(UsageEvent(id=identifier,user_id=me.id,family_id=family_id,create_by=me.id,create_date=now,**values))
    s.commit()
    return {'ok':True,'accepted':len(new)}


def _rate(success,count):return round(100*success/count,1) if count else None


def build_report(year,week):
    year,week,start,end=report_period(week,year);s=get_session();now=local_now()
    visits=s.query(FamilyVisit).filter(FamilyVisit.first_seen_at>=start,FamilyVisit.first_seen_at<end,
                                     FamilyVisit.cohort_eligible.is_(True),FamilyVisit.del_flag==0).all()
    mature=[row for row in visits if row.first_seen_at+dt.timedelta(days=7)<=now]
    saved=sum(bool(row.first_saved_at and row.first_seen_at<=row.first_saved_at<=row.first_seen_at+dt.timedelta(days=7)) for row in mature)
    published=sum(bool(row.first_published_at and row.first_seen_at<=row.first_published_at<=row.first_seen_at+dt.timedelta(days=7)) for row in mature)
    events=s.query(UsageEvent).filter(UsageEvent.create_date>=start,UsageEvent.create_date<end,UsageEvent.del_flag==0).all()
    client={}
    for kind in ('retention','restore'):
        sample=[row for row in events if row.kind==kind];success=sum(row.outcome=='success' for row in sample)
        client[kind]=dict(count=len(sample),success=success,rate=_rate(success,len(sample)))
    corrections=s.query(StoryCorrection.status,StoryCorrection.create_date,StoryCorrection.reviewed_at).filter(StoryCorrection.create_date>=start,StoryCorrection.create_date<end,StoryCorrection.del_flag==0).all()
    handled=[row for row in corrections if row.status in ('accepted','rejected')]
    durations=[(row.reviewed_at-row.create_date).total_seconds()/3600 for row in handled if row.reviewed_at and row.reviewed_at>=row.create_date]
    verifications=s.query(VerificationItem.status,VerificationItem.create_date,VerificationItem.resolved_at).filter(VerificationItem.create_date>=start,VerificationItem.create_date<end,VerificationItem.del_flag==0).all()
    resolved=sum(row.status=='resolved' for row in verifications)
    verification_durations=[(row.resolved_at-row.create_date).total_seconds()/3600 for row in verifications
                           if row.status=='resolved' and row.resolved_at and row.resolved_at>=row.create_date]
    expected=s.query(StoryPublication.id,StoryPublication.family_id).join(Interview,Interview.id==StoryPublication.id).join(Family,Family.id==Interview.family_id).filter(
        StoryPublication.published_at>=start,StoryPublication.published_at<end,Interview.del_flag==0,Family.del_flag==0,
        Interview.visibility.in_(('public',)) | Interview.visibility.is_(None),
        Interview.publish_status.in_(('published',)) | Interview.publish_status.is_(None)).all()
    from views import _weekly_data
    reported={}
    for family_id in {row.family_id for row in expected}:
        reported[family_id]={story.id for story in _weekly_data(family_id,week,year=year,include_extras=False)['interviews']}
    missing=sum(row.id not in reported.get(row.family_id,set()) for row in expected)
    legacy=s.query(Interview.id).join(Family,Family.id==Interview.family_id).filter(Family.del_flag==0,Interview.del_flag==0,Interview.published_at.is_(None),
        Interview.create_date>=start,Interview.create_date<end,
        Interview.visibility.in_(('public',)) | Interview.visibility.is_(None),
        Interview.publish_status.in_(('published',)) | Interview.publish_status.is_(None)).count()
    turns=s.query(AiTurn.id,AiTurn.family_id,AiTurn.user_id,AiTurn.status,AiTurn.logical_id,AiTurn.create_date,AiTurn.sources).filter(AiTurn.create_date<=now,AiTurn.del_flag==0).all()
    groups={}
    for turn in turns:
        if turn.logical_id:groups.setdefault((turn.user_id,turn.family_id,turn.logical_id),[]).append(turn)
    failed=0;recovered=0
    for attempts in groups.values():
        failures=[row for row in attempts if row.status in ('failed','cancelled')]
        if not failures:continue
        first=min(row.create_date for row in failures)
        if not start<=first<end:continue
        failed+=1
        recovered+=any(row.status=='succeeded' and row.create_date>=first for row in attempts)
    current_stories={row.id:row for row in s.query(Interview.id,Interview.family_id,Interview.visibility,Interview.publish_status).filter_by(del_flag=0).all()}
    source_count=0;available=0;members={}
    active_users={row.id for row in s.query(User.id).filter_by(del_flag=0).all()}
    for turn in turns:
        if turn.status!='succeeded' or not start<=turn.create_date<end:continue
        key=(turn.family_id,turn.user_id)
        if key not in members:members[key]=turn.user_id in active_users and bool(family_role(s,*key))
        for source in turn.sources or []:
            source_count+=1
            story=current_stories.get(source.get('story_id')) if isinstance(source,dict) else None
            available+=bool(members[key] and story and story.family_id==turn.family_id and
                            (story.visibility or 'public')=='public' and (story.publish_status or 'published')=='published')
    samples=s.query(MetricSample).filter_by(year=year,week=week,del_flag=0).all()
    manual={}
    for kind in ('source_support','elder_task'):
        rows=[row for row in samples if row.kind==kind];count=sum(row.sample_count for row in rows)
        success=sum(row.success_count for row in rows);assisted=sum(row.assisted_success for row in rows)
        manual[kind]=dict(count=count,success=success,assisted=assisted,rate=_rate(success,count),independent_rate=_rate(success-assisted,count))
    return dict(year=year,week=week,as_of=now,conversion=dict(observed=len(visits),mature=len(mature),saved=saved,published=published,
        saved_rate=_rate(saved,len(mature)),published_rate=_rate(published,len(mature))),client=client,
        corrections=dict(count=len(corrections),handled=len(handled),rate=_rate(len(handled),len(corrections)),
                         hours=round(sum(durations)/len(durations),1) if durations else None),
        verifications=dict(count=len(verifications),resolved=resolved,rate=_rate(resolved,len(verifications)),
                           timed=len(verification_durations),hours=round(sum(verification_durations)/len(verification_durations),1) if verification_durations else None),
        weekly=dict(checked=len(expected),missing=missing if expected else None,legacy=legacy),
        ai=dict(failed=failed,recovered=recovered,rate=_rate(recovered,failed),source_count=source_count,
                available_rate=_rate(available,source_count),legacy=sum(not row.logical_id and start<=row.create_date<end for row in turns)),
        manual=manual,samples=s.query(MetricSample).filter_by(year=year,week=week).order_by(MetricSample.create_date.desc(),MetricSample.id).limit(100).all())


@bp.route('/operations/metrics',methods=['GET','POST'])
def dashboard():
    me=_current_user();require_operator(me)
    default_year,default_week=current_period()
    try:year=int(request.args.get('year',default_year));week=int(request.args.get('week',default_week));report_period(week,year)
    except (ValueError,TypeError,OverflowError):abort(400)
    s=get_session()
    if request.method=='POST':
        require_csrf()
        if request.form.get('action')=='void':
            reason=request.form.get('reason')
            if reason not in ('输入错误','重复记录','非真实样本'):abort(400)
            changed=s.query(MetricSample).filter_by(id=request.form.get('sample_id'),del_flag=0).update({MetricSample.del_flag:1,
                MetricSample.void_reason:reason,MetricSample.update_by:me.id,MetricSample.update_date:local_now()},synchronize_session=False)
            if changed!=1:s.rollback();abort(409)
        else:
            kind=request.form.get('kind');task=request.form.get('task','') if kind=='elder_task' else ''
            device=request.form.get('device','').strip() if kind=='elder_task' else ''
            evidence=request.form.get('evidence_ref','').strip().lower();nonce=request.form.get('nonce','')
            try:count=int(request.form.get('sample_count',''));success=int(request.form.get('success_count',''));assisted=int(request.form.get('assisted_success','0')) if kind=='elder_task' else 0
            except ValueError:abort(400)
            if kind not in ('source_support','elder_task') or (kind=='elder_task' and (task not in TASKS or not device)) or len(device)>80:abort(400)
            if not 1<=count<=1000 or not 0<=assisted<=success<=count:abort(400)
            if not re.fullmatch(r'[A-Za-z0-9._-]{1,80}',evidence) or not re.fullmatch(r'[A-Za-z0-9_-]{8,80}',nonce):abort(400)
            identifier=hashlib.sha256((me.id+'\0'+nonce).encode()).hexdigest()
            values=dict(year=year,week=week,kind=kind,task=task,device=device,evidence_ref=evidence,
                        sample_count=count,success_count=success,assisted_success=assisted)
            existing=s.query(MetricSample).filter_by(id=identifier).first()
            if existing:
                if any(getattr(existing,key)!=value for key,value in values.items()):abort(409)
            else:
                s.add(MetricSample(id=identifier,create_by=me.id,create_date=local_now(),**values))
                try:s.flush()
                except IntegrityError:s.rollback();abort(409,'证据编号已记录，请勿重复统计')
        s.commit()
        return redirect(url_for('metrics.dashboard',year=year,week=week))
    return render_template('metrics.html',report=build_report(year,week),tasks=TASKS,nonce=secrets.token_urlsafe(24),
                           collection=collection_enabled())
