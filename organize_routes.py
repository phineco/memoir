"""Private materials and explicit user actions; all mutations require CSRF."""
import io
import math
import secrets
from pathlib import Path

from flask import Blueprint, abort, redirect, render_template, request, send_file, url_for
from werkzeug.exceptions import HTTPException

from forms import require_csrf
from models import OrganizeRecord, Person, get_session
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


def material_page(family_id, record_id=None):
    me, s = _current_user(), get_session()
    family = _family_or_404(family_id)
    record = organizing.owned(s, family_id, me.id, record_id) if record_id else None
    values, error, status = {}, None, 200
    if request.method == 'POST':
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
    return render_template('organize.html', family=family, record=record, values=values,
        error=error, people=people, nonce=values.get('nonce') or secrets.token_urlsafe(24),
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
