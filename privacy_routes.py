import hashlib
import math
import re
import secrets

from flask import Blueprint,abort,current_app,redirect,render_template,request,url_for
from sqlalchemy.exc import IntegrityError

from forms import require_csrf
from models import PrivacyRequest,PrivacyResponse,User,get_session,new_id
from operations import require_operator
from reporting import local_now
from views import _current_user,_family_or_404


bp=Blueprint('privacy',__name__)
KINDS={'ai':'AI 对话与记忆','account':'账号注销','data':'资料更正或删除','other':'其他隐私事项'}
STATUSES={'submitted':'已提交','processing':'处理中','needs_info':'待补充资料','completed':'已处理完成','rejected':'无法处理（见说明）','withdrawn':'本人已撤回'}
CLOSED=('completed','rejected','withdrawn')


def _user():
    me=_current_user()
    if not me:abort(401)
    return me


def _page(query,oldest=False):
    try:page=int(request.args.get('page','1'))
    except ValueError:abort(400)
    if page<1:abort(400)
    total=query.count();pages=max(1,math.ceil(total/20));page=min(page,pages)
    ordering=(PrivacyRequest.first_response_at.isnot(None),PrivacyRequest.create_date,PrivacyRequest.id) if oldest else (PrivacyRequest.create_date.desc(),PrivacyRequest.id)
    return query.order_by(*ordering).limit(20).offset((page-1)*20).all(),page,pages


@bp.route('/account/privacy-requests',methods=['GET','POST'])
def requests_list():
    me=_current_user()
    if not me:return redirect(url_for('main.login',next=request.full_path.rstrip('?')))
    family_id=request.args.get('family_id');fam=_family_or_404(family_id) if family_id else None
    s=get_session();error=None
    enabled=s.query(User.id).filter(User.id.in_(current_app.config.get('OPERATIONS_USER_IDS',())),User.del_flag==0).first() is not None
    if request.method=='POST':
        require_csrf()
        if not enabled:abort(503,'站内申请尚未启用，请使用隐私联系邮箱')
        kind=request.form.get('kind');details=request.form.get('details','').strip();nonce=request.form.get('nonce','')
        if kind not in KINDS or not 1<=len(details)<=2000 or not re.fullmatch(r'[A-Za-z0-9_-]{8,80}',nonce):
            error='请选择申请事项并填写不超过 2000 字的说明。'
        else:
            identifier=hashlib.sha256((me.id+'\0'+nonce).encode()).hexdigest()
            s.query(User).filter_by(id=me.id,del_flag=0).with_for_update().one()
            existing=s.query(PrivacyRequest).filter_by(id=identifier,user_id=me.id).with_for_update().populate_existing().first()
            if existing:
                if existing.kind!=kind or existing.details!=details:abort(409)
                return redirect(url_for('privacy.request_detail',request_id=identifier))
            if len(s.query(PrivacyRequest.id).filter(PrivacyRequest.user_id==me.id,PrivacyRequest.status.notin_(CLOSED)).with_for_update().all())>=5:
                error='已有 5 项申请正在处理，请在原申请中补充信息。'
            else:
                item=PrivacyRequest(id=identifier,user_id=me.id,kind=kind,details=details,status='submitted',revision=1,create_by=me.id,create_date=local_now())
                s.add(item)
                try:s.commit()
                except IntegrityError:
                    s.rollback();prior=s.query(PrivacyRequest).filter_by(id=identifier,user_id=me.id).one()
                    if prior.details!=details or prior.kind!=kind:abort(409)
                return redirect(url_for('privacy.request_detail',request_id=identifier))
    rows,page,pages=_page(s.query(PrivacyRequest).filter_by(user_id=me.id,del_flag=0))
    return render_template('privacy_requests.html',family=fam,rows=rows,page=page,pages=pages,kinds=KINDS,statuses=STATUSES,
        error=error,enabled=enabled,nonce=request.form.get('nonce') or secrets.token_urlsafe(24),form=request.form,
        page_url=lambda value:url_for('privacy.requests_list',page=value,family_id=family_id)),400 if error else 200


def _transition(item,actor,operator):
    s=get_session()
    try:revision=int(request.form.get('revision',''))
    except ValueError:abort(400)
    item=s.query(PrivacyRequest).filter_by(id=item.id,del_flag=0).with_for_update().populate_existing().one()
    if item.revision!=revision or item.status in CLOSED:abort(409,'申请已有新进度，请刷新后核对')
    content=request.form.get('content','').strip()
    status=request.form.get('status') if operator else ('withdrawn' if request.form.get('action')=='withdraw' else 'submitted')
    if not operator and status=='withdrawn':content='本人撤回此申请。'
    if not 1<=len(content)<=2000 or status not in STATUSES or (operator and status not in ('processing','needs_info','completed','rejected')):abort(400)
    now=local_now();verified=item.identity_verified_at
    if operator and request.form.get('verified')=='yes':verified=verified or now
    if operator and status=='completed' and not verified:abort(400,'完成前须确认已核验身份并实际处理')
    values={PrivacyRequest.status:status,PrivacyRequest.revision:revision+1,PrivacyRequest.update_date:now,
            PrivacyRequest.resolved_at:now if status in CLOSED else None}
    if operator:
        values[PrivacyRequest.first_response_at]=item.first_response_at or now
        values[PrivacyRequest.identity_verified_at]=verified
    changed=s.query(PrivacyRequest).filter_by(id=item.id,revision=revision).update(values,synchronize_session=False)
    if changed!=1:s.rollback();abort(409)
    s.add(PrivacyResponse(id=new_id(),request_id=item.id,actor_role='operator' if operator else 'user',
                          revision=revision+1,status=status,content=content,create_by=actor.id,create_date=now))
    s.commit()


def _detail(identifier,operator=False):
    me=_user()
    if operator:require_operator(me)
    query=get_session().query(PrivacyRequest).filter_by(id=identifier,del_flag=0)
    if not operator:query=query.filter_by(user_id=me.id)
    item=query.first()
    if not item:abort(404)
    if request.method=='POST':
        require_csrf();_transition(item,me,operator)
        return redirect(url_for('privacy.operation_detail' if operator else 'privacy.request_detail',request_id=identifier))
    replies=get_session().query(PrivacyResponse).filter_by(request_id=item.id,del_flag=0).order_by(PrivacyResponse.revision,PrivacyResponse.id).all()
    return render_template('privacy_request_detail.html',item=item,replies=replies,kinds=KINDS,statuses=STATUSES,closed=CLOSED,operator=operator)


@bp.route('/account/privacy-requests/<request_id>',methods=['GET','POST'])
def request_detail(request_id):return _detail(request_id)


@bp.route('/operations/privacy')
def operations_list():
    require_operator(_user())
    status=request.args.get('status','open')
    if status not in ('open','all',*STATUSES):abort(400)
    query=get_session().query(PrivacyRequest).filter_by(del_flag=0)
    if status=='open':query=query.filter(PrivacyRequest.status.notin_(CLOSED))
    elif status!='all':query=query.filter_by(status=status)
    rows,page,pages=_page(query,oldest=status=='open')
    return render_template('privacy_operations.html',rows=rows,statuses=STATUSES,kinds=KINDS,status=status,page=page,pages=pages,
                           page_url=lambda value:url_for('privacy.operations_list',page=value,status=status))


@bp.route('/operations/privacy/<request_id>',methods=['GET','POST'])
def operation_detail(request_id):return _detail(request_id,operator=True)
