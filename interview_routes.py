"""Interview pages use the same family membership and author-only material boundary."""
import secrets

from flask import Blueprint, abort, redirect, render_template, request, url_for, send_file, jsonify, current_app
import io
from forms import require_csrf
from werkzeug.exceptions import HTTPException
from models import InterviewSession, InterviewQuestion, InterviewClip, Person, get_session
import interviewing
from views import _current_user, _family_or_404, _families_for_user

bp = Blueprint('interview', __name__)


@bp.before_request
def authenticate():
    if not _current_user():
        if request.method == 'GET': return redirect(url_for('main.login', next=request.full_path.rstrip('?')))
        abort(401)
    if request.method == 'POST':
        request.max_content_length = current_app.config['INTERVIEW_MAX_UPLOAD_BYTES']+128*1024 if request.endpoint=='interview.upload' else 1024*1024
        require_csrf()


@bp.after_request
def private(response):
    response.headers['Cache-Control'] = 'private, no-store'
    return response


@bp.route('/account/interviews')
@bp.route('/f/<family_id>/interviews')
def index(family_id=None):
    family = _family_or_404(family_id) if family_id else None
    families = [family] if family else _families_for_user(_current_user())
    rows = get_session().query(InterviewSession).filter_by(user_id=_current_user().id, del_flag=0).filter(InterviewSession.family_id.in_([f.id for f in families])).order_by(InterviewSession.update_date.desc()).limit(50).all()
    return render_template('interviews.html', family=family, rows=rows, families=families)


@bp.route('/f/<family_id>/interview/new', methods=['GET', 'POST'])
def new(family_id):
    family = _family_or_404(family_id); s = get_session()
    if request.method == 'POST':
        row = interviewing.start(s, family_id, _current_user().id, request.form, request.form.get('nonce'))
        return redirect(url_for('interview.detail', family_id=family_id, session_id=row.id))
    people = s.query(Person).filter_by(family_id=family_id, del_flag=0).order_by(Person.sort, Person.name).all()
    from interview_questions import enabled
    return render_template('interview_new.html', ai_enabled=enabled(), family=family, people=people, topics=interviewing.TOPICS, nonce=secrets.token_urlsafe(24))


@bp.route('/f/<family_id>/interview/<session_id>')
def detail(family_id, session_id):
    return render_detail(family_id, session_id)


def render_detail(family_id, session_id, error=None):
    family = _family_or_404(family_id); s = get_session()
    row = interviewing.owned(s, family_id, _current_user().id, session_id)
    import interview_audio
    clips=s.query(InterviewClip).filter_by(session_id=row.id,del_flag=0).filter(InterviewClip.status.notin_(('deleting','deleted'))).order_by(InterviewClip.create_date).all()
    latest = s.query(InterviewQuestion).filter_by(session_id=row.id).order_by(InterviewQuestion.create_date.desc()).first()
    return render_template('interview.html', family=family, interview=row, clips=clips, local_identity=interview_audio.local_identity(_current_user().id), recorder_user=_current_user().id, answers=interviewing.answers(s, row.id),
        topics=interviewing.TOPICS, nonce=secrets.token_urlsafe(24), pending=interviewing.pending(s, row), latest_question=latest,
        error=error.description if error else None, values=request.form if error else {}), error.code if error else 200


@bp.route('/f/<family_id>/interview/<session_id>/action', methods=['POST'])
def action(family_id, session_id):
    name = request.form.get('action')
    args = (get_session(), family_id, _current_user().id, session_id, request.form.get('revision'))
    try:
        if name in ('pause','resume'): interviewing.pause(*args, resume=name=='resume')
        elif name in ('answer','skip'):
            interviewing.answer(*args, request.form.get('nonce'), request.form.get('answer',''), skip=name=='skip')
        elif name == 'topic': interviewing.switch_topic(*args, request.form.get('topic'))
        elif name == 'template': interviewing.use_template(*args)
        elif name == 'edit': interviewing.edit_answer(*args, request.form.get('answer_id'), request.form.get('answer_version'), request.form.get('answer',''))
        elif name == 'finish':
            row = interviewing.finish(*args)
            return redirect(url_for('organize.detail',family_id=family_id,record_id=row.record_id))
        else: abort(400, '操作无效')
        return redirect(url_for('interview.detail', family_id=family_id, session_id=session_id))
    except HTTPException as exc:
        get_session().rollback()
        if exc.code not in (400,409,429): raise
        return render_detail(family_id, session_id, error=exc)


@bp.get('/account/interview-identity')
def identity():
    return jsonify(user_id=_current_user().id)


@bp.post('/f/<family_id>/interview/<session_id>/upload')
def upload(family_id,session_id):
    import interview_audio
    file=request.files.get('audio')
    if not file: abort(400,'请选择录音文件')
    try:
        clip=interview_audio.upload(get_session(),family_id,_current_user().id,session_id,request.form.get('revision'),
            request.form.get('nonce'),file.read(current_app.config['INTERVIEW_MAX_UPLOAD_BYTES']+1),request.form.get('consent_recording')=='yes')
    except HTTPException as exc:
        get_session().rollback()
        if request.headers.get('Accept')=='application/json': return jsonify(error=exc.description),exc.code
        raise
    if request.headers.get('Accept')=='application/json': return jsonify(id=clip.id,status=clip.status)
    return redirect(url_for('interview.detail',family_id=family_id,session_id=session_id))


@bp.get('/f/<family_id>/interview/<session_id>/audio/<clip_id>')
def audio(family_id,session_id,clip_id):
    import interview_audio
    clip=interview_audio.owned_clip(get_session(),family_id,_current_user().id,session_id,clip_id)
    return send_file(io.BytesIO(interview_audio.read(clip.storage_key)),mimetype='audio/wav',as_attachment=request.args.get('download')=='1',download_name='采访原声-'+clip.id+'.wav')
