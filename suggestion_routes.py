from flask import Blueprint,abort,redirect,render_template,request,url_for
from forms import require_csrf
from access import family_role
from models import NewPerson,Person,Interview,get_session
import people_suggestions
from views import _current_user,_family_or_404

bp=Blueprint('suggestions',__name__)


@bp.before_request
def authenticate():
    if not _current_user():
        if request.method=='GET':return redirect(url_for('main.login',next=request.path))
        abort(401)
    if request.method=='POST':require_csrf()


@bp.after_request
def private(response):
    response.headers['Cache-Control']='private, no-store';return response


@bp.get('/f/<family_id>/people/suggestions')
def index(family_id):
    family=_family_or_404(family_id);s=get_session()
    if family_role(s,family_id,_current_user().id) not in ('owner','admin'):abort(403)
    query=s.query(NewPerson).join(Interview,NewPerson.interview_id==Interview.id).filter(NewPerson.family_id==family_id,
        NewPerson.del_flag==0,NewPerson.source_record_id.isnot(None),NewPerson.join_tree=='pending',
        Interview.del_flag==0,Interview.publish_status=='published',Interview.visibility=='public')
    try:page=int(request.args.get('page','1'))
    except ValueError:abort(400)
    pages=max(1,(query.count()+19)//20)
    if not 1<=page<=pages:abort(404)
    rows=[]
    for candidate in query.order_by(NewPerson.create_date.desc(),NewPerson.id).offset((page-1)*20).limit(20):
        if people_suggestions.readable(s,candidate):
            story,draft=people_suggestions.public_story(s,family_id,candidate.interview_id)
            rows.append((candidate,story,draft.version))
    people=s.query(Person).filter_by(family_id=family_id,del_flag=0).order_by(Person.name,Person.id).all()
    return render_template('people_suggestions.html',family=family,rows=rows,people=people,page=page,pages=pages)


@bp.post('/f/<family_id>/people/suggestions/<candidate_id>')
def review(family_id,candidate_id):
    people_suggestions.review(get_session(),family_id,_current_user().id,candidate_id,request.form.get('story_version'),
        request.form.get('action'),request.form.get('person_id'),request.form.get('name',''),request.form.get('duplicate')=='yes')
    return redirect(url_for('suggestions.index',family_id=family_id))


@bp.post('/f/<family_id>/plans/suggestions/<suggestion_id>')
def plan_review(family_id,suggestion_id):
    import plan_suggestions
    plan_suggestions.review(get_session(),family_id,_current_user().id,suggestion_id,request.form.get('action'))
    return redirect(url_for('main.plan_list',family_id=family_id))
