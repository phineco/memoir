"""Task-focused elder pages share the same private services and permissions."""
from urllib.parse import urlsplit,urlunsplit

from flask import Blueprint,abort,current_app,redirect,render_template,request,session,url_for
from models import InterviewSession,OrganizeRecord,Interview,Draft,Person,get_session
from access import story_visible
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


@bp.get('/easy/families')
def families():
    return render_template('easy_choose.html',family=None,families=_families_for_user(_current_user()))


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



@bp.get('/easy/listen')
def listen():
    family,response=selected()
    if response:return response
    from views import _visible_filter,_published_only
    s=get_session()
    query=_visible_filter(s.query(Interview).filter_by(family_id=family.id,del_flag=0).filter(_published_only()),s,_current_user())
    import re
    value=request.args.get('page','1')
    if not re.fullmatch(r'[1-9][0-9]{0,4}',value):abort(400)
    page=int(value);pages=max(1,(query.count()+19)//20)
    if page>pages:abort(404)
    stories=query.order_by(Interview.published_at.desc(),Interview.create_date.desc(),Interview.id).offset((page-1)*20).limit(20).all()
    return render_template('easy_listen.html',family=family,stories=stories,page=page,pages=pages)


@bp.get('/easy/f/<family_id>/story/<story_id>')
def story(family_id,story_id):
    family=_family_or_404(family_id);s=get_session()
    row=s.query(Interview).filter_by(id=story_id,family_id=family_id,del_flag=0).first()
    if not row or not story_visible(s,row,_current_user().id,include_drafts=False):abort(404)
    draft=s.query(Draft).filter_by(interview_id=row.id,is_current=True,del_flag=0).order_by(Draft.version.desc()).first()
    from voices import story_context
    return render_template('easy_story.html',family=family,iv=row,draft=draft,**story_context(row,_current_user()))


@bp.get('/easy/photos')
def photos():
    family,response=selected()
    if response:return response
    from album import query_photos,uploader_info,date_label
    photos,location,page,pages,total,uploader,filters=query_photos(family.id)
    options,labels=uploader_info(family.id,uploader)
    people=get_session().query(Person).filter_by(family_id=family.id,del_flag=0).order_by(Person.sort,Person.name).all()
    def page_url(number):
        values=request.args.to_dict();values.update(family_id=family.id,page=number);return url_for('easy.photos',**values)
    return render_template('easy_photos.html',family=family,photos=photos,location=location,page=page,pages=pages,total=total,
        uploader=uploader,filters=filters,uploader_options=options,uploader_names=labels,people=people,date_label=date_label,page_url=page_url)


@bp.get('/easy/f/<family_id>/photo/<photo_id>')
def photo(family_id,photo_id):
    from album import photo_or_404,date_label,uploader_info
    family=_family_or_404(family_id);row=photo_or_404(family_id,photo_id);options,labels=uploader_info(family_id)
    return render_template('easy_photo.html',family=family,photo=row,date_label=date_label,uploader_names=labels)


@bp.get('/easy/settings')
def settings():
    family,response=selected()
    if response:return response
    return render_template('easy_settings.html',family=family)


@bp.get('/easy/help')
def help():
    family,response=selected()
    if response:return response
    return render_template('easy_help.html',family=family)

def adapt_url(value):
    parsed=urlsplit(value)
    if parsed.netloc and parsed.netloc!=request.host:return value
    parts=parsed.path.split('/')
    if len(parts)>3 and parts[1]=='f' and parts[3] in ('interview','interviews','organize'):
        return urlunsplit((parsed.scheme,parsed.netloc,'/easy'+parsed.path,parsed.query,parsed.fragment))
    return value


def install(app):
    app.register_blueprint(bp)
    from pwa import install as install_pwa
    install_pwa(app)
    # Alias the existing views, including their blueprint authentication/CSRF hooks.
    # Data and task services remain one implementation; URLs carry the chosen task interface.
    for rule in list(app.url_map.iter_rules()):
        if rule.endpoint.startswith(('interview.','organize.')) and rule.rule.startswith('/f/'):
            app.add_url_rule('/easy'+rule.rule,endpoint=rule.endpoint,view_func=app.view_functions[rule.endpoint],methods=list(rule.methods-{'HEAD','OPTIONS'}))
    @app.before_request
    def gate():
        if not (request.path=='/easy' or request.path.startswith('/easy/')):return
        if not app.config.get('EASY_ENABLED'):abort(404)
        if request.path in ('/easy/manifest.webmanifest','/easy/sw.js'):
            if not app.config.get('EASY_PWA_ENABLED'):abort(404)
            return
        if request.path=='/easy/login':return
        me=_current_user()
        if not me:return redirect(url_for('easy_pwa.login',next=request.full_path.rstrip('?')))
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
            full=values.pop('_full',False)
            if not active or full:return url_for(endpoint,**values)
            mapped={'main.stories':'easy.listen','main.account':'easy.settings','main.display_preferences':'easy.settings','main.guide':'easy.help'}
            if endpoint in mapped:return url_for(mapped[endpoint],family_id=values.get('family_id'))
            if endpoint=='interview.index':return url_for('easy.records',family_id=values.get('family_id'))
            return adapt_url(url_for(endpoint,**values))
        return {'easy_mode':active,'easy_enabled':app.config.get('EASY_ENABLED'),'easy_pwa_enabled':bool(app.config.get('EASY_ENABLED') and app.config.get('EASY_PWA_ENABLED')),**({'url_for':flow_url} if active else {})}
