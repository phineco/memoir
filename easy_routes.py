"""Task-focused elder pages share the same private services and permissions."""
from urllib.parse import urlsplit,urlunsplit

from flask import Blueprint,abort,current_app,redirect,render_template,request,session,url_for
from models import InterviewSession,OrganizeRecord,Interview,get_session
from views import _current_user,_families_for_user,_family_or_404

bp=Blueprint('easy',__name__)


def resolve():
    me=_current_user();families=_families_for_user(me);valid={f.id:f for f in families}
    explicit=request.args.get('family_id')
    if explicit:
        if explicit not in valid:abort(404)
        fid=explicit
    else:
        saved=session.get('easy_family') or {}
        fid=saved.get('id') if isinstance(saved,dict) and saved.get('user')==me.id else None
        if fid not in valid:fid=next(iter(valid)) if len(valid)==1 else None
    if fid:session['easy_family']={'user':me.id,'id':fid}
    else:session.pop('easy_family',None)
    return valid.get(fid),families


def selected():
    family,families=resolve()
    if not family:return None,render_template('easy_choose.html',family=None,families=families)
    return family,None


@bp.get('/easy')
def index():
    family,response=selected()
    if response:return response
    row=get_session().query(InterviewSession).filter_by(family_id=family.id,user_id=_current_user().id,del_flag=0).filter(
        InterviewSession.state.in_(('active','paused'))).order_by(InterviewSession.update_date.desc(),InterviewSession.id).first()
    return render_template('easy_home.html',family=family,continuing=row)


@bp.get('/easy/records')
def records():
    family,response=selected()
    if response:return response
    s=get_session();uid=_current_user().id
    interviews=s.query(InterviewSession).filter_by(family_id=family.id,user_id=uid,del_flag=0).filter(InterviewSession.state!='deleted').order_by(InterviewSession.update_date.desc()).limit(20).all()
    materials=s.query(OrganizeRecord).filter_by(family_id=family.id,user_id=uid,del_flag=0,story_id=None).order_by(OrganizeRecord.update_date.desc()).limit(20).all()
    drafts=s.query(Interview).filter_by(family_id=family.id,author_id=uid,del_flag=0,publish_status='draft').order_by(Interview.update_date.desc()).limit(20).all()
    return render_template('easy_records.html',family=family,interviews=interviews,materials=materials,drafts=drafts)


@bp.get('/easy/tell')
def tell():
    family,response=selected()
    if response:return response
    return redirect(adapt_url(url_for('interview.new',family_id=family.id)))


def adapt_url(value):
    parsed=urlsplit(value)
    if parsed.netloc and parsed.netloc!=request.host:return value
    parts=parsed.path.split('/')
    if len(parts)>3 and parts[1]=='f' and parts[3] in ('interview','interviews','organize'):
        return urlunsplit((parsed.scheme,parsed.netloc,'/easy'+parsed.path,parsed.query,parsed.fragment))
    return value


def install(app):
    app.register_blueprint(bp)
    # Alias the existing views, including their blueprint authentication/CSRF hooks.
    # Data and task services remain one implementation; URLs carry the chosen task interface.
    for rule in list(app.url_map.iter_rules()):
        if rule.endpoint.startswith(('interview.','organize.')) and rule.rule.startswith('/f/'):
            app.add_url_rule('/easy'+rule.rule,endpoint=rule.endpoint,view_func=app.view_functions[rule.endpoint],methods=list(rule.methods-{'HEAD','OPTIONS'}))
    @app.before_request
    def gate():
        if not (request.path=='/easy' or request.path.startswith('/easy/')):return
        if not app.config.get('EASY_ENABLED'):abort(404)
        me=_current_user()
        if not me:return redirect(url_for('main.login',next=request.full_path.rstrip('?')))
        fid=(request.view_args or {}).get('family_id')
        if fid:
            _family_or_404(fid);session['easy_family']={'user':me.id,'id':fid}
    @app.after_request
    def private(response):
        if request.path=='/easy' or request.path.startswith('/easy/'):
            response.headers['Cache-Control']='private, no-store'
            if response.status_code in (301,302,303,307,308) and response.headers.get('Location'):
                response.headers['Location']=adapt_url(response.headers['Location'])
        return response
    @app.context_processor
    def context():
        active=request.path=='/easy' or request.path.startswith('/easy/')
        def flow_url(endpoint,**values):
            if not active:return url_for(endpoint,**values)
            if endpoint=='interview.index':return url_for('easy.records',family_id=values.get('family_id'))
            return adapt_url(url_for(endpoint,**values))
        return {'easy_mode':active,'easy_enabled':app.config.get('EASY_ENABLED'),**({'url_for':flow_url} if active else {})}
