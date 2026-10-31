"""Private materials and explicit user actions; all mutations require CSRF."""
import io
import math
import secrets
from pathlib import Path

from flask import Blueprint, abort, redirect, render_template, request, send_file, url_for
from werkzeug.exceptions import HTTPException

from forms import require_csrf
from models import OrganizeRecord, OrganizeTask, Person, get_session
import organizing
from views import _current_user, _family_or_404, _families_for_user

bp = Blueprint('organize', __name__)


@bp.before_request
def authenticate():
    if not _current_user():
        if request.method == 'GET':
            return redirect(url_for('main.login', next=request.full_path.rstrip('?')))
        abort(401)
    if request.method == 'POST':
        request.max_content_length = organizing.MAX_FILE + 128 * 1024
        require_csrf()


@bp.after_request
def private(response):
    response.headers['Cache-Control'] = 'private, no-store'
    return response


@bp.route('/account/organize')
@bp.route('/f/<family_id>/organize')
def index(family_id=None):
    me = _current_user()
    family = _family_or_404(family_id) if family_id else None
    families = _families_for_user(me)
    by_id = {f.id: f for f in families}
    s = get_session()
    query = s.query(OrganizeRecord).filter_by(user_id=me.id, del_flag=0).filter(
        OrganizeRecord.family_id.in_([family.id] if family else list(by_id)))
    try:
        page = max(1, int(request.args.get('page', '1')))
    except ValueError:
        abort(400)
    pages = max(1, math.ceil(query.count() / 20))
    page = min(page, pages)
    rows = [(r, by_id[r.family_id]) for r in query.order_by(OrganizeRecord.update_date.desc(), OrganizeRecord.id).limit(20).offset((page-1)*20)]
    return render_template('organize_list.html', family=family, rows=rows, page=page, pages=pages,
                           page_url=lambda value: url_for('organize.index', family_id=family_id, page=value))


def material_input():
    values = request.form.to_dict()
    file = request.files.get('source')
    if file and file.filename:
        if values.get('content', '').strip():
            abort(400, '请只保留文字或文件其中一种；已有文字不会被覆盖。')
        if Path(file.filename).suffix.lower() not in ('.txt', '.md'):
            abort(400, '只支持 UTF-8 的 .txt/.md 文字文件')
        raw = file.read(organizing.MAX_FILE + 1)
        if len(raw) > organizing.MAX_FILE:
            abort(413, '文字文件最多 1 MiB，请拆分后上传')
        try:
            values['content'] = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            abort(400, '请将文字文件另存为 UTF-8 编码后上传')
    return values


def material_page(family_id, record_id=None, action_error=None):
    me, s = _current_user(), get_session()
    family = _family_or_404(family_id)
    record = organizing.owned(s, family_id, me.id, record_id) if record_id else None
    values, error, status = {}, action_error.description if action_error else None, action_error.code if action_error else 200
    if request.method == 'POST' and action_error is None:
        values = request.form.to_dict()
        try:
            values = material_input()
            if record:
                saved = organizing.update(s, family_id, me.id, record.id, values.get('revision'), values)
            else:
                saved = organizing.create(s, family_id, me.id, values, nonce=values.get('nonce'))
            return redirect(url_for('organize.detail', family_id=family_id, record_id=saved.id, saved=1))
        except HTTPException as exc:
            if exc.code not in (400, 409, 413):
                raise
            s.rollback()
            error, status = exc.description, exc.code
    people = s.query(Person).filter_by(family_id=family_id, del_flag=0).order_by(Person.sort, Person.name).all()
    import organize_jobs
    from people_suggestions import source_context
    followup=source_context(s,record)
    from plan_suggestions import options
    plan_options=options(s,record)
    task = s.query(OrganizeTask).filter_by(record_id=record.id, user_id=me.id).order_by(OrganizeTask.create_date.desc(), OrganizeTask.id.desc()).first() if record else None
    return render_template('organize.html', family=family, record=record, values=values,
        error=error, followup=followup, plan_options=plan_options, people=people, task=task, task_message=organize_jobs.MESSAGES.get(task.status) if task else None,
        ai_enabled=organize_jobs.enabled(), preview_values=request.form if action_error else {}, nonce=values.get('nonce') or secrets.token_urlsafe(24),
        notice='原稿已保存，仅自己可见。' if request.args.get('saved') == '1' else None), status


@bp.route('/f/<family_id>/organize/new', methods=['GET', 'POST'])
def new(family_id):
    return material_page(family_id)


@bp.route('/f/<family_id>/organize/<record_id>', methods=['GET', 'POST'])
def detail(family_id, record_id):
    return material_page(family_id, record_id)


@bp.route('/f/<family_id>/organize/<record_id>/source')
def export(family_id, record_id):
    record = organizing.owned(get_session(), family_id, _current_user().id, record_id)
    return send_file(io.BytesIO(record.content.encode('utf-8')), mimetype='text/plain',
                     as_attachment=True, download_name='家音原稿-'+record.id+'.txt')


@bp.route('/f/<family_id>/organize/<record_id>/delete', methods=['POST'])
def remove(family_id, record_id):
    if request.form.get('confirm') != 'yes':
        abort(400, '请明确确认删除原材料')
    organizing.delete(get_session(), family_id, _current_user().id, record_id, acknowledge_story=True)
    return redirect(url_for('organize.index', family_id=family_id))


@bp.route('/f/<family_id>/organize/<record_id>/action', methods=['POST'])
def action(family_id, record_id):
    import organize_jobs
    import organize_preview
    me, s = _current_user(), get_session()
    try:
        name = request.form.get('action')
        if name == 'generate':
            organize_jobs.begin(family_id, me.id, record_id, request.form.get('revision'), request.form.get('nonce'),
                consent=request.form.get('consent') == 'yes', regenerate=request.form.get('regenerate') == 'yes')
        elif name == 'cancel':
            organize_jobs.cancel(family_id, me.id, record_id, request.form.get('task_id'))
        elif name == 'plan-suggest':
            import plan_suggestions
            plan_suggestions.propose(s,family_id,me.id,record_id,request.form.get('plan_id'),request.form.get('item_index'),request.form.get('plan_stamp'),request.form.get('story_version'))
        elif name == 'share-people':
            import people_suggestions
            if request.form.get('confirm_share')!='yes':abort(400,'请确认只分享已公开故事中的人物依据。')
            people_suggestions.share(s,family_id,me.id,record_id,request.form.get('revision'),request.form.get('preview_revision'),request.form.get('story_version'),request.form.getlist('people_index'))
        elif name == 'confirm':
            import organize_drafts
            if request.form.get('confirm_review') != 'yes': abort(400, '请先确认已经核对预览。')
            story = organize_drafts.confirm(s, family_id, me.id, record_id, request.form.get('revision'),
                request.form.get('preview_revision'), request.form.get('nonce'), request.form.getlist('related_ids'))
            return redirect(url_for('main.edit_article', family_id=family_id, interview_id=story.id))
        elif name in ('manual', 'preview'):
            args = (s, family_id, me.id, record_id, request.form.get('revision'), request.form.get('preview_revision'))
            if name == 'manual': organize_preview.manual(*args)
            else: organize_preview.save(*args, request.form)
        else:
            abort(400, '操作无效')
        return redirect(url_for('organize.detail', family_id=family_id, record_id=record_id))
    except HTTPException as exc:
        s.rollback()
        if exc.code not in (400, 409, 429): raise
        return material_page(family_id, record_id, action_error=exc)
