"""Opt-in account defaults; device overrides remain local and scoped to one account."""
from flask import Blueprint,abort,current_app,g,jsonify,request,session
from sqlalchemy.exc import IntegrityError
from forms import require_csrf
from models import User,UserDisplayPreference,get_session
from reporting import local_now

bp=Blueprint('display_preferences',__name__)
CHOICES={'theme':('modern','paper','contrast'),'font':('sans','serif','rounded'),'size':('18','22','26'),
    'mode':('standard','simple'),'entry':('standard','easy')}


def current_user():
    uid=session.get('user_id');me=get_session().get(User,uid) if uid else None
    return me if me and me.del_flag==0 else None


def payload(me):
    enabled=bool(current_app.config.get('DISPLAY_ACCOUNT_SYNC_ENABLED') and me)
    row=get_session().query(UserDisplayPreference).filter_by(user_id=me.id,del_flag=0).first() if enabled else None
    return {'user':me.id if me else '', 'enabled':enabled,'revision':row.revision if row else 0,
        'values':row.preferences if row else None,'easyEnabled':bool(current_app.config.get('EASY_ENABLED'))}


@bp.before_request
def authenticate():
    if not current_user():abort(401)
    if not current_app.config.get('DISPLAY_ACCOUNT_SYNC_ENABLED'):abort(404)
    if request.method=='POST':
        request.max_content_length=16384;require_csrf()


@bp.after_request
def private(response):response.headers['Cache-Control']='private, no-store';return response


@bp.route('/account/display-preferences',methods=['GET','POST'])
def preference():
    me=current_user();s=get_session()
    if request.method=='GET':return jsonify(payload(me))
    data=request.get_json(silent=True)
    if not isinstance(data,dict) or set(data)!={'values','base_revision','expected_user_id'}:abort(400,'显示设置格式无效，请重新打开设置页。')
    if data['expected_user_id']!=me.id:abort(409,'当前登录账号已变化，请重新打开本人设置页。')
    values=data['values'];revision=data['base_revision']
    if not isinstance(values,dict) or set(values)!=set(CHOICES) or any(values[key] not in choices for key,choices in CHOICES.items()):abort(400,'请选择可用的显示选项。')
    if type(revision) is not int or not 0<=revision<2147483647:abort(400,'设置版本无效。')
    from transaction_locks import serialize_sqlite
    serialize_sqlite(s,me.id)
    if not s.query(User).filter_by(id=me.id,del_flag=0).with_for_update().first():abort(401)
    row=s.query(UserDisplayPreference).filter_by(user_id=me.id).with_for_update().populate_existing().first()
    if row and row.preferences==values and not row.del_flag:
        s.commit();return jsonify(payload(me))
    if (row.revision if row else 0)!=revision:abort(409,'账号默认设置已被另一台设备更新；请先读取核对，不会覆盖较新设置。')
    if not row:
        row=UserDisplayPreference(id=me.id,user_id=me.id,revision=1,preferences=values,create_by=me.id)
        s.add(row)
    else:
        row.preferences=values;row.revision+=1;row.del_flag=0;row.update_by=me.id;row.update_date=local_now()
    try:s.commit()
    except IntegrityError:
        s.rollback();abort(409,'设置刚刚更新，请读取账号默认后核对。')
    return jsonify(payload(me))


def install(app):
    app.register_blueprint(bp)
    @app.context_processor
    def context():
        if not hasattr(g,'display_bootstrap'):g.display_bootstrap=payload(current_user())
        return {'display_bootstrap':g.display_bootstrap,'display_sync_enabled':g.display_bootstrap['enabled']}
