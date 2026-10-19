"""路由：页面（Jinja2 服务端渲染）+ 周报聚合 API + 登录/评论/点赞。"""
import datetime
import json
import re

from flask import Blueprint, abort, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from models import (Comment, Draft, Family, FamilyMember, Interview, InterviewPerson,
                    InterviewViewer, Invite, Like, NewPerson, Person, PersonLink, Photo, Portrait, Quote,
                    ShareSnapshot, SyncLog, TimelineEvent, User, VerificationItem,
                    WritingPlan, get_session)

bp = Blueprint("main", __name__)

STATUS_LABEL = {
    "pending": "⏳待采访", "doing": "📝整理中",
    "drafted": "✅初稿完成", "verified": "✔️已核实定稿",
}


def _s():
    return get_session()


def _current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return _s().query(User).filter_by(id=uid, del_flag=0).first()


# ---------- 登录（原型：手机号+密码；生产换微信 OAuth） ----------

@bp.route("/register", methods=["GET", "POST"])
def register():
    import sms as sms_mod
    invite_code = request.args.get("invite") or request.form.get("invite_code") or ""
    inv = _valid_invite(invite_code) if invite_code else None
    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        nickname = request.form.get("nickname", "").strip() or phone
        password = request.form.get("password", "")
        code = request.form.get("code", "").strip()
        s = _s()
        if not phone or not password:
            return render_template("register.html", error="手机号和密码不能为空",
                                   invite_code=invite_code, invite=inv,
                                   sms_enabled=sms_mod.sms_enabled())
        import re as _re
        if not _re.fullmatch(r"\d{11}", phone):
            return render_template("register.html", error="手机号应为 11 位数字",
                                   invite_code=invite_code, invite=inv,
                                   sms_enabled=sms_mod.sms_enabled())
        if len(password) < 6:
            return render_template("register.html", error="密码至少 6 位",
                                   invite_code=invite_code, invite=inv,
                                   sms_enabled=sms_mod.sms_enabled())
        if s.query(User).filter_by(phone=phone, del_flag=0).first():
            return render_template("register.html", error="该手机号已注册",
                                   invite_code=invite_code, invite=inv,
                                   sms_enabled=sms_mod.sms_enabled())
        try:
            sms_mod.verify_code(phone, code, "register")
        except sms_mod.SMSError as e:
            return render_template("register.html", error=str(e),
                                   invite_code=invite_code, invite=inv,
                                   sms_enabled=sms_mod.sms_enabled(),
                                   form=request.form)
        from models import new_id
        u = User(id=new_id(), phone=phone, nickname=nickname,
                 password_hash=generate_password_hash(password))
        s.add(u)
        s.flush()
        if inv:
            _join_family(s, inv.family_id, u.id, u.id)
            inv.used_count = (inv.used_count or 0) + 1
            s.commit()
        else:
            s.commit()
        session["user_id"] = u.id
        if inv:
            return redirect(url_for("main.family_home",
                                    family_id=inv.family_id))
        return redirect(request.args.get("next") or url_for("main.index"))
    return render_template("register.html", invite_code=invite_code, invite=inv,
                           sms_enabled=sms_mod.sms_enabled())


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        from sqlalchemy import or_
        login_id = request.form.get("phone", "").strip()  # 手机号或用户名
        password = request.form.get("password", "")
        s = _s()
        u = s.query(User).filter(
            User.del_flag == 0,
            or_(User.phone == login_id, User.username == login_id)).first()
        if not u or not u.password_hash or not check_password_hash(u.password_hash, password):
            return render_template("login.html", error="登录名或密码不正确")
        session["user_id"] = u.id
        return redirect(request.args.get("next") or url_for("main.index"))
    return render_template("login.html")


@bp.route("/logout")
def logout():
    session.pop("user_id", None)
    return redirect(url_for("main.index"))


# ---------- 评论（树形） ----------

def _comment_tree(interview_id):
    s = _s()
    comments = s.query(Comment).filter_by(interview_id=interview_id, del_flag=0)\
        .order_by(Comment.create_date).all()
    users = {}
    if comments:
        for u in s.query(User).filter(
                User.id.in_([c.user_id for c in comments]), User.del_flag == 0).all():
            users[u.id] = u
    nodes = {c.id: {"c": c, "children": []} for c in comments}
    roots = []
    for c in comments:
        if c.parent_id == "0" or c.parent_id not in nodes:
            roots.append(nodes[c.id])
        else:
            nodes[c.parent_id]["children"].append(nodes[c.id])
    return roots, users


@bp.route("/f/<family_id>/story/<interview_id>/comment", methods=["POST"])
def post_comment(family_id, interview_id):
    u = _current_user()
    if not u:
        return redirect(url_for("main.login", next=request.path))
    _family_or_404(family_id)
    s = _s()
    iv = s.query(Interview).filter_by(id=interview_id, family_id=family_id, del_flag=0).first()
    if not iv:
        abort(404)
    me = _current_user()
    if not _can_view(iv, me):
        abort(404)
    content = request.form.get("content", "").strip()
    parent_id = request.form.get("parent_id", "0") or "0"
    if content:
        from models import new_id
        s.add(Comment(id=new_id(), interview_id=interview_id, user_id=u.id,
                      parent_id=parent_id, content=content[:2000]))
        s.commit()
    return redirect(url_for("main.story_detail", family_id=family_id,
                            interview_id=interview_id))


# ---------- 点赞 ----------

@bp.route("/api/like", methods=["POST"])
def api_like():
    u = _current_user()
    if not u:
        return jsonify({"ok": False, "need_login": True}), 401
    data = request.get_json(force=True)
    ttype, tid = data.get("target_type"), data.get("target_id")
    if ttype not in ("interview", "comment") or not tid:
        return jsonify({"ok": False}), 400
    s = _s()
    from models import new_id
    like = s.query(Like).filter_by(target_type=ttype, target_id=tid,
                                   user_id=u.id, del_flag=0).first()
    if like:
        like.del_flag = 1
        liked = False
    else:
        s.add(Like(id=new_id(), target_type=ttype, target_id=tid, user_id=u.id))
        liked = True
    count = s.query(Like).filter_by(target_type=ttype, target_id=tid, del_flag=0).count()
    if ttype == "interview":
        iv = s.query(Interview).filter_by(id=tid).first()
        if iv:
            iv.like_count = count
    else:
        c = s.query(Comment).filter_by(id=tid).first()
        if c:
            c.like_count = count
    s.commit()
    return jsonify({"ok": True, "liked": liked, "count": count})


def _cal(v):
    """日历类型校验：只接受 solar/lunar，其他按 solar。"""
    return v if v in ("solar", "lunar") else "solar"


def _family_or_404(family_id):
    s = _s()
    fam = s.query(Family).filter_by(id=family_id, del_flag=0).first()
    if not fam:
        abort(404)
    return fam


def _person_or_404(family_id, person_id):
    s = _s()
    p = s.query(Person).filter_by(id=person_id, family_id=family_id, del_flag=0).first()
    if not p:
        abort(404)
    return p


def _week_of(dt):
    return dt.isocalendar()[1] if dt else None


def _can_view(iv, me):
    """草稿仅作者可见；已发布按 visibility：public 所有人可见，private 仅作者，specific 作者+白名单。"""
    if (iv.publish_status or "published") != "published":
        return bool(me and iv.author_id == me.id)
    vis = iv.visibility or "public"
    if vis == "public":
        return True
    if not me:
        return False
    if iv.author_id == me.id:
        return True
    if vis == "specific":
        s = _s()
        return s.query(InterviewViewer).filter_by(
            interview_id=iv.id, user_id=me.id, del_flag=0).first() is not None
    return False


def _published_only():
    from sqlalchemy import or_
    return or_(Interview.publish_status == "published",
               Interview.publish_status.is_(None))


def _visible_filter(q, s, me):
    """故事列表 SQL 过滤：已发布且公开；或作者自己的（含草稿/私有）；或被指定可见的。"""
    from sqlalchemy import or_, and_
    pub = _published_only()
    conds = [and_(pub, or_(Interview.visibility == "public",
                           Interview.visibility.is_(None)))]
    if me:
        conds.append(Interview.author_id == me.id)
        conds.append(and_(
            pub, Interview.visibility == "specific",
            Interview.id.in_(
                s.query(InterviewViewer.interview_id).filter_by(
                    user_id=me.id, del_flag=0))))
    return q.filter(or_(*conds))


def _family_member_users(s, family_id):
    """家庭成员用户列表（指定可见人多选框用）。返回 [(user_id, 显示名)]。"""
    rows = s.query(FamilyMember, User).join(
        User, FamilyMember.user_id == User.id
    ).filter(FamilyMember.family_id == family_id,
             FamilyMember.del_flag == 0, User.del_flag == 0).all()
    return [(u.id, u.nickname or u.phone or u.username or u.id)
            for m, u in rows]


def _save_visibility(s, iv, form, family_id, me):
    """保存故事可见性：visibility + specific 时的白名单（先清后写）。"""
    from models import new_id
    vis = form.get("visibility", "public")
    if vis not in ("public", "private", "specific"):
        vis = "public"
    iv.visibility = vis
    for v in s.query(InterviewViewer).filter_by(
            interview_id=iv.id, del_flag=0).all():
        v.del_flag = 1
        v.update_by = me.id
        v.update_date = datetime.datetime.now()
    if vis == "specific":
        member_ids = {uid for uid, _ in _family_member_users(s, family_id)}
        for uid in form.getlist("viewer_ids"):
            if uid and uid in member_ids and uid != me.id:
                s.add(InterviewViewer(id=new_id(), interview_id=iv.id,
                                      user_id=uid, create_by=me.id,
                                      create_date=datetime.datetime.now()))
    return vis


def _published_filter(q):
    from sqlalchemy import or_
    return q.filter(or_(Interview.publish_status == "published",
                        Interview.publish_status.is_(None)))


def _unit(pid, by_id):
    """夫妻归一：有配偶的人物折叠为同一辈分单元（取较小 id 作代表）。"""
    p = by_id.get(pid)
    if p and p.spouse_id and p.spouse_id in by_id:
        return min(pid, p.spouse_id)
    return pid


def _uchain(pid, by_id):
    """在辈分单元上建祖先链（夫妻只记一次）。"""
    ch, seen = [], set()
    while pid and pid != "0" and pid not in seen:
        seen.add(pid)
        p = by_id.get(pid)
        if not p:
            break
        u = _unit(pid, by_id)
        if not ch or ch[-1] != u:
            ch.append(u)
        pid = p.parent_id
    return ch


def _gend(p):
    g = (p.gender or "").upper()
    return "M" if g in ("M", "男") else ("F" if g in ("F", "女") else None)


def kinship_term(viewer_id, target_id, by_id):
    """算 target 相对 viewer 的称谓。缺性别/辈分信息时返回中性词或 None。"""
    if viewer_id == target_id:
        return "我"
    V, X = by_id.get(viewer_id), by_id.get(target_id)
    if not V or not X:
        return None
    if _unit(viewer_id, by_id) == _unit(target_id, by_id):
        return {"M": "丈夫", "F": "妻子"}.get(_gend(X), "配偶")
    vc, xc = _uchain(viewer_id, by_id), _uchain(target_id, by_id)
    vpos = {u: i for i, u in enumerate(vc)}
    lca = next((u for u in xc if u in vpos), None)
    if not lca:
        return None
    u, d = vpos[lca], xc.index(lca)
    gx = _gend(X)

    def _raw(uid):
        for pid, p in by_id.items():
            if _unit(pid, by_id) == uid:
                return p
        return None

    def older(a, b):
        if a and b and a.birth_year and b.birth_year:
            return a.birth_year < b.birth_year
        return None

    if d == 0:  # X 是 V 的长辈
        if u == 1:
            return {"M": "父亲", "F": "母亲"}.get(gx, "父母")
        if u in (2, 3):
            P = _raw(vc[1])
            pat = P and _gend(P) == "M"
            mat = P and _gend(P) == "F"
            if u == 2:
                if pat:
                    return {"M": "祖父", "F": "祖母"}.get(gx, "祖父母")
                if mat:
                    return {"M": "外祖父", "F": "外祖母"}.get(gx, "外祖父母")
                return "祖父母"
            if pat:
                return {"M": "曾祖父", "F": "曾祖母"}.get(gx, "曾祖父母")
            if mat:
                return {"M": "外曾祖父", "F": "外曾祖母"}.get(gx, "外曾祖父母")
            return "曾祖父母"
        return "祖先"
    if u == 0:  # X 是 V 的晚辈
        if d == 1:
            return {"M": "儿子", "F": "女儿"}.get(gx, "子女")
        if d == 2:
            C = _raw(xc[1])
            cm = C and _gend(C) == "M"
            cf = C and _gend(C) == "F"
            if cm:
                return {"M": "孙子", "F": "孙女"}.get(gx, "孙子女")
            if cf:
                return {"M": "外孙", "F": "外孙女"}.get(gx, "外孙子女")
            return "孙子女"
        return "后代"
    if u == 1 and d == 1:  # 同辈
        o = older(X, V)
        if gx == "M":
            return {True: "哥哥", False: "弟弟"}.get(o, "兄弟")
        if gx == "F":
            return {True: "姐姐", False: "妹妹"}.get(o, "姐妹")
        return "兄弟姐妹"
    if u == 2 and d == 1:  # 父母的兄弟姐妹
        P = _raw(vc[1])
        pm = P and _gend(P) == "M"
        pf = P and _gend(P) == "F"
        o = older(X, P)
        if pm:
            if gx == "M":
                return {True: "伯父", False: "叔父"}.get(o, "伯叔")
            if gx == "F":
                return "姑母"
            return "伯叔姑"
        if pf:
            if gx == "M":
                return "舅父"
            if gx == "F":
                return "姨母"
            return "舅姨"
        return "父辈"
    if u == 1 and d == 2:  # 兄弟姐妹的子女
        S = _raw(xc[1])
        sm = S and _gend(S) == "M"
        sf = S and _gend(S) == "F"
        if sm:
            return {"M": "侄子", "F": "侄女"}.get(gx, "侄子女")
        if sf:
            return {"M": "外甥", "F": "外甥女"}.get(gx, "外甥子女")
        return "侄甥"
    if u == 2 and d == 2:
        return "堂表兄弟姐妹"
    return None



def _build_tree(family_id, viewer_id=None):
    """persons 表 parent_id 树 → ECharts tree 所需嵌套结构。"""
    s = _s()
    persons = s.query(Person).filter_by(family_id=family_id, del_flag=0).order_by(Person.sort).all()
    users = {u.id: u.nickname or u.phone for u in s.query(User).filter_by(del_flag=0).all()}
    by_id = {p.id: p for p in persons}
    nodes = {}
    for p in persons:
        lines = [p.name]
        # 出生/去世年月（只有年份数据时显示年份；农历加前缀）
        if p.birth_year and p.death_year:
            lines.append(f"{p.birth_label}–{p.death_label}")
        elif p.birth_year:
            lines.append(f"{p.birth_label}年生" if p.alive else f"生于{p.birth_label}")
        elif p.death_year:
            lines.append(f"卒于{p.death_label}")
        if p.aliases:
            lines.append("别名：" + "、".join(p.aliases))
        if p.user_id and p.user_id in users:
            lines.append(f"👤{users[p.user_id]}")
        kin = kinship_term(viewer_id, p.id, by_id) if viewer_id else None
        if kin:
            lines.append(f"对你：{kin}")
        elif p.relation:
            lines.append(f"（{p.relation}）")
        nodes[p.id] = {
            "name": "\n".join(lines), "person_id": p.id,
            "itemStyle": {"color": "#b7d7a8" if p.alive else "#d9d9d9"},
            "children": [],
        }
    root = None
    for p in persons:
        node = nodes[p.id]
        if p.parent_id == "0" or p.parent_id not in nodes:
            root = node
        else:
            nodes[p.parent_id]["children"].append(node)
    return root or {"name": "（空）", "children": []}


@bp.route("/")
def index():
    s = _s()
    families = s.query(Family).filter_by(del_flag=0).all()
    return render_template("index.html", families=families)


@bp.route("/f/<family_id>")
def family_home(family_id):
    fam = _family_or_404(family_id)
    s = _s()
    n_person = s.query(Person).filter_by(family_id=family_id, del_flag=0).count()
    n_story = s.query(Interview).filter_by(family_id=family_id, del_flag=0).count()
    n_pending = s.query(VerificationItem).join(
        Interview, VerificationItem.interview_id == Interview.id
    ).filter(Interview.family_id == family_id,
             VerificationItem.status == "pending",
             VerificationItem.del_flag == 0).count()
    week = datetime.date.today().isocalendar()[1]
    me = _current_user()
    viewer = s.query(Person).filter_by(family_id=family_id, user_id=me.id,
                                       del_flag=0).first() if me else None
    member_rows = s.query(FamilyMember, User).join(
        User, FamilyMember.user_id == User.id
    ).filter(FamilyMember.family_id == family_id,
             FamilyMember.del_flag == 0, User.del_flag == 0)\
     .order_by(FamilyMember.role).all()
    member_user_ids = {m.user_id for m, u in member_rows}
    cand_users = [u for u in s.query(User).filter_by(del_flag=0).all()
                  if u.id not in member_user_ids]
    # 可重置密码的目标：创建者→所有人；管理员→普通成员
    is_owner_now = _is_owner(fam, me)
    is_admin_now = _is_admin(fam, me)
    resettable_ids = set()
    if me and is_admin_now:
        for m, u in member_rows:
            if is_owner_now or m.role == "member":
                resettable_ids.add(u.id)
    invites = s.query(Invite).filter_by(
        family_id=family_id, del_flag=0).order_by(
        Invite.create_date.desc()).limit(10).all()
    return render_template("family.html", family=fam,
                           tree=_build_tree(family_id, viewer.id if viewer else None),
                           n_person=n_person, n_story=n_story,
                           n_pending=n_pending, week=week,
                           status_label=STATUS_LABEL, me=me,
                           is_admin=is_admin_now, is_owner=is_owner_now,
                           member_rows=member_rows, cand_users=cand_users,
                           resettable_ids=resettable_ids,
                           invites=invites,
                           new_invite=session.pop("new_invite", None),
                           created_account=session.pop("created_account", None),
                           reset_notice=session.pop("reset_notice", None),
                           member_form_error=session.pop("member_form_error", None))


def _person_page_ctx(family_id, p, me):
    s = _s()
    portrait = s.query(Portrait).filter_by(person_id=p.id, del_flag=0)\
        .order_by(Portrait.version.desc()).first()
    photos = s.query(Photo).filter_by(person_id=p.id, del_flag=0)\
        .order_by(Photo.photo_year).all()
    events = s.query(TimelineEvent).filter_by(person_id=p.id, del_flag=0)\
        .order_by(TimelineEvent.event_date).all()
    by_year, undated = {}, []
    for e in events:
        if e.event_date:
            by_year.setdefault(e.event_date.year, []).append(e)
        else:
            undated.append(e)
    iq = s.query(Interview).filter_by(family_id=family_id, del_flag=0).filter(
        (Interview.person_id == p.id) |
        (Interview.id.in_(
            s.query(InterviewPerson.interview_id).filter_by(
                person_id=p.id, del_flag=0)))
    )
    iq = _visible_filter(iq, s, me)
    interviews = iq.order_by(Interview.create_date.desc()).all()
    linked_user = s.query(User).filter_by(id=p.user_id).first() if p.user_id else None
    my_link = s.query(Person).filter_by(family_id=family_id, user_id=me.id,
                                        del_flag=0).first() if me else None
    kinship = None
    if me and my_link:
        by_id = {x.id: x for x in s.query(Person).filter_by(
            family_id=family_id, del_flag=0).all()}
        kinship = kinship_term(my_link.id, p.id, by_id)
    return dict(portrait=portrait, photos=photos, by_year=by_year, undated=undated,
                interviews=interviews, status_label=STATUS_LABEL, me=me,
                is_admin=_is_admin(_family_or_404(family_id), me),
                linked_user=linked_user, my_link=my_link, kinship=kinship)


@bp.route("/f/<family_id>/person/<person_id>")
def person_page(family_id, person_id):
    fam = _family_or_404(family_id)
    p = _person_or_404(family_id, person_id)
    me = _current_user()
    return render_template("person.html", family=fam, person=p,
                           **_person_page_ctx(family_id, p, me))


@bp.route("/f/<family_id>/stories")
def stories(family_id):
    fam = _family_or_404(family_id)
    s = _s()
    me = _current_user()
    q = s.query(Interview, Person).outerjoin(
        Person, Interview.person_id == Person.id
    ).filter(Interview.family_id == family_id, Interview.del_flag == 0)
    q = _visible_filter(q, s, me)
    rows = q.order_by(Interview.create_date.desc()).all()
    return render_template("stories.html", family=fam, rows=rows, me=me)


@bp.route("/f/<family_id>/story/<interview_id>")
def story_detail(family_id, interview_id):
    fam = _family_or_404(family_id)
    s = _s()
    iv = s.query(Interview).filter_by(id=interview_id, family_id=family_id, del_flag=0).first()
    if not iv:
        abort(404)
    me = _current_user()
    if not _can_view(iv, me):
        abort(404)
    # 观看数：同会话去重（生产用 Redis/IP 去重）
    viewed = session.setdefault("viewed", [])
    if interview_id not in viewed:
        iv.view_count = (iv.view_count or 0) + 1
        viewed.append(interview_id)
        session["viewed"] = viewed
        s.commit()
    person = s.query(Person).filter_by(id=iv.person_id).first() if iv.person_id else None
    narrator = s.query(Person).filter_by(id=iv.narrator_person_id).first() \
        if iv.narrator_person_id else None
    draft = s.query(Draft).filter_by(interview_id=interview_id, is_current=True, del_flag=0).first()
    quotes = s.query(Quote).filter_by(interview_id=interview_id, del_flag=0).all()
    verifs = s.query(VerificationItem).filter_by(interview_id=interview_id, del_flag=0).all()
    links = s.query(PersonLink).filter_by(interview_id=interview_id, del_flag=0).all()
    comment_roots, comment_users = _comment_tree(interview_id)
    me = _current_user()
    liked_ids = set()
    if me:
        for lk in s.query(Like).filter_by(user_id=me.id, del_flag=0).all():
            liked_ids.add((lk.target_type, lk.target_id))
    # 关联人物（人物线串联）
    rel_rows = s.query(InterviewPerson, Person).join(
        Person, InterviewPerson.person_id == Person.id
    ).filter(InterviewPerson.interview_id == interview_id,
             InterviewPerson.del_flag == 0, Person.del_flag == 0)\
     .order_by(InterviewPerson.role.desc()).all()
    return render_template("story.html", family=fam, iv=iv, person=person, draft=draft,
                           quotes=quotes, verifs=verifs, links=links,
                           comment_roots=comment_roots, comment_users=comment_users,
                           me=me, liked_ids=liked_ids, rel_rows=rel_rows,
                           narrator=narrator, is_admin=_is_admin(fam, me))


def _weekly_data(family_id, week, viewer_id=None):
    """周报数据。viewer_id 传入时只含该用户可见的故事；不传则只含公开故事。"""
    s = _s()
    interviews = s.query(Interview).filter_by(family_id=family_id, del_flag=0).all()
    if viewer_id:
        visible_ids = {v.interview_id for v in s.query(InterviewViewer).filter_by(
            user_id=viewer_id, del_flag=0).all()}
    else:
        visible_ids = set()

    def _ok(iv):
        if _week_of(iv.create_date) != week:
            return False
        if (iv.publish_status or "published") != "published":
            return False
        vis = iv.visibility or "public"
        if vis == "public":
            return True
        if not viewer_id or iv.author_id == viewer_id:
            return bool(viewer_id and iv.author_id == viewer_id)
        return vis == "specific" and iv.id in visible_ids

    interviews = [iv for iv in interviews if _ok(iv)]
    iv_ids = [iv.id for iv in interviews]
    verifs, quotes, new_persons = [], [], []
    if iv_ids:
        verifs = s.query(VerificationItem).filter(
            VerificationItem.interview_id.in_(iv_ids),
            VerificationItem.del_flag == 0).all()
        quotes = s.query(Quote).filter(
            Quote.interview_id.in_(iv_ids), Quote.del_flag == 0).all()
    new_persons = s.query(NewPerson).filter_by(family_id=family_id, del_flag=0).all()
    new_persons = [np for np in new_persons if _week_of(np.create_date) == week]
    persons = {p.id: p for p in
               s.query(Person).filter_by(family_id=family_id, del_flag=0).all()}
    return {"interviews": interviews, "verifs": verifs, "quotes": quotes,
            "new_persons": new_persons, "persons": persons}


@bp.route("/f/<family_id>/weekly")
def weekly_current(family_id):
    week = datetime.date.today().isocalendar()[1]
    return redirect(url_for("main.weekly_report", family_id=family_id, week=week))


@bp.route("/f/<family_id>/weekly/<int:week>")
def weekly_report(family_id, week):
    fam = _family_or_404(family_id)
    me = _current_user()
    data = _weekly_data(family_id, week, viewer_id=me.id if me else None)
    import ai as ai_mod
    ai_summary = ai_mod.get_weekly_summary(family_id, week) \
        if ai_mod.ai_enabled() else None
    return render_template("weekly.html", family=fam, week=week, **data,
                           ai_summary=ai_summary,
                           ai_enabled=ai_mod.ai_enabled(),
                           is_admin=_is_admin(fam, me))


def _weekly_report_json(family_id, week, viewer_id=None):
    """周报聚合数据（流水线设计 v0.4 §三）：API 与分享快照共用。不传 viewer 只含公开故事。"""
    data = _weekly_data(family_id, week, viewer_id=viewer_id)
    persons = data.pop("persons")
    return {
        "family_id": family_id, "week": week,
        "stories": [{"id": iv.id, "topic": iv.topic,
                     "person": persons[iv.person_id].name if iv.person_id in persons else None,
                     "narrator": persons[iv.narrator_person_id].name if iv.narrator_person_id in persons else None,
                     "period": {"start": iv.period_start.isoformat() if iv.period_start else None,
                                "end": iv.period_end.isoformat() if iv.period_end else None,
                                "precision": iv.period_precision},
                     "status": iv.status} for iv in data["interviews"]],
        "quotes": [q.text for q in data["quotes"]],
        "verification_items": [
            {"id": v.id, "text": v.text, "reason": v.reason, "status": v.status,
             "correction": v.correction} for v in data["verifs"]],
        "new_persons": [{"name": np.name, "context": np.context,
                         "join_tree": np.join_tree} for np in data["new_persons"]],
        "unsynced_count": 0,
    }


@bp.route("/api/weekly-report")
def api_weekly_report():
    """周报聚合接口（流水线设计 v0.4 §三）。"""
    family_id = request.args.get("family_id")
    week = int(request.args.get("week", datetime.date.today().isocalendar()[1]))
    _family_or_404(family_id)
    data = _weekly_report_json(family_id, week)
    # unsynced_count：本周同步失败、待人工处理的条数（读同步状态表）
    s = _s()
    failed = s.query(SyncLog).filter_by(family_id=family_id,
                                        status="failed").all()
    data["unsynced_count"] = sum(
        1 for l in failed if l.create_date and _week_of(l.create_date) == week)
    return jsonify(data)


@bp.route("/s/<token>", methods=["GET", "POST"])
def share_page(token):
    s = _s()
    snap = s.query(ShareSnapshot).filter_by(token=token, del_flag=0).first()
    if not snap:
        abort(404)
    if (snap.status or "published") != "published":
        abort(404)  # 待确认的快照不对外开放
    if snap.expires_at and snap.expires_at < datetime.datetime.now():
        abort(410)
    authed = session.get("share_authed") == token
    if request.method == "POST":
        pwd = request.form.get("password", "")
        if snap.password_hash and check_password_hash(snap.password_hash, pwd):
            session["share_authed"] = token
            authed = True
        else:
            return render_template("share.html", need_password=True, error="密码不正确", snap=snap)
    if not authed and snap.password_hash:
        return render_template("share.html", need_password=True, snap=snap)
    return render_template("share.html", need_password=False, snap=snap,
                           content=snap.content_json or {})


# ---------------- 分享管理（管理员）：生成快照 → 人工确认发布 ----------------

@bp.route("/f/<family_id>/shares")
def share_list(family_id):
    """分享管理页：待确认快照与已发布列表（仅管理员）。"""
    me = _current_user()
    fam = _family_or_404(family_id)
    if not _is_admin(fam, me):
        abort(403)
    s = _s()
    snaps = s.query(ShareSnapshot).filter_by(family_id=family_id, del_flag=0)\
        .order_by(ShareSnapshot.create_date.desc()).all()
    return render_template("shares.html", family=fam, snaps=snaps, me=me,
                           error=request.args.get("error"))


@bp.route("/f/<family_id>/shares/new", methods=["POST"])
def share_new(family_id):
    """从当前周报生成快照：先存为待确认，不对外开放。"""
    me = _current_user()
    fam = _family_or_404(family_id)
    if not _is_admin(fam, me):
        abort(403)
    import re as _re
    s = _s()
    week = datetime.date.today().isocalendar()[1]
    rj = _weekly_report_json(family_id, week)
    drafts = {d.interview_id: d for d in s.query(Draft).filter(
        Draft.interview_id.in_([st["id"] for st in rj["stories"]]),
        Draft.is_current == True, Draft.del_flag == 0).all()}  # noqa: E712
    stories = []
    for st in rj["stories"]:
        summary = ""
        d = drafts.get(st["id"])
        if d and d.content:
            text = _re.sub(r"<[^>]+>", "", d.content)
            summary = text.strip()[:120]
        stories.append({"title": st["topic"], "person": st["person"] or "",
                        "narrator": st["narrator"] or "", "summary": summary})
    title = f"{fam.name} · 回忆录（第{week}周）"
    from models import new_id
    snap = ShareSnapshot(
        id=new_id(), family_id=family_id, title=title, status="draft",
        content_json={"title": title, "stories": stories,
                      "quotes": rj["quotes"],
                      "tree_note": f"本周新增 {len(stories)} 篇故事，金句 {len(rj['quotes'])} 条"},
        create_by=me.id, create_date=datetime.datetime.now())
    s.add(snap)
    s.commit()
    return redirect(url_for("main.share_preview", family_id=family_id,
                            snap_id=snap.id))


@bp.route("/f/<family_id>/shares/<snap_id>")
def share_preview(family_id, snap_id):
    """快照预览（管理员）：所见即发布后的样子。"""
    me = _current_user()
    fam = _family_or_404(family_id)
    if not _is_admin(fam, me):
        abort(403)
    s = _s()
    snap = s.query(ShareSnapshot).filter_by(id=snap_id, family_id=family_id,
                                            del_flag=0).first()
    if not snap:
        abort(404)
    return render_template("share.html", snap=snap, need_password=False,
                           content=snap.content_json or {}, preview=True,
                           family=fam, me=me)


@bp.route("/f/<family_id>/shares/<snap_id>/publish", methods=["POST"])
def share_publish(family_id, snap_id):
    """人工确认发布：生成随机 token + 设置访问密码后才对外生效。"""
    me = _current_user()
    fam = _family_or_404(family_id)
    if not _is_admin(fam, me):
        abort(403)
    s = _s()
    snap = s.query(ShareSnapshot).filter_by(id=snap_id, family_id=family_id,
                                            del_flag=0).first()
    if not snap:
        abort(404)
    password = request.form.get("password", "").strip()
    if len(password) < 4:
        return redirect(url_for("main.share_list", family_id=family_id,
                                error="访问密码至少 4 位"))
    import secrets
    snap.token = secrets.token_urlsafe(16)
    snap.password_hash = generate_password_hash(password)
    snap.status = "published"
    snap.update_by = me.id
    snap.update_date = datetime.datetime.now()
    s.commit()
    return redirect(url_for("main.share_list", family_id=family_id))


@bp.route("/f/<family_id>/shares/<snap_id>/unpublish", methods=["POST"])
def share_unpublish(family_id, snap_id):
    """下线：链接立即失效，退回待确认。"""
    me = _current_user()
    fam = _family_or_404(family_id)
    if not _is_admin(fam, me):
        abort(403)
    s = _s()
    snap = s.query(ShareSnapshot).filter_by(id=snap_id, family_id=family_id,
                                            del_flag=0).first()
    if not snap:
        abort(404)
    snap.status = "draft"
    snap.update_by = me.id
    snap.update_date = datetime.datetime.now()
    s.commit()
    return redirect(url_for("main.share_list", family_id=family_id))


@bp.route("/f/<family_id>/shares/<snap_id>/delete", methods=["POST"])
def share_delete(family_id, snap_id):
    me = _current_user()
    fam = _family_or_404(family_id)
    if not _is_admin(fam, me):
        abort(403)
    s = _s()
    snap = s.query(ShareSnapshot).filter_by(id=snap_id, family_id=family_id,
                                            del_flag=0).first()
    if not snap:
        abort(404)
    snap.del_flag = 1
    snap.update_by = me.id
    snap.update_date = datetime.datetime.now()
    s.commit()
    return redirect(url_for("main.share_list", family_id=family_id))



# ---------------- 写文章（登录用户） ----------------

@bp.route("/f/<family_id>/write", methods=["GET", "POST"])
def write_article(family_id):
    me = _current_user()
    if not me:
        return redirect(url_for("main.login", next=request.path))
    fam = _family_or_404(family_id)
    s = _s()
    persons = s.query(Person).filter_by(family_id=family_id, del_flag=0)\
        .order_by(Person.sort).all()
    # 讲述者默认 = 作者在树上认领的人物（"这是我"）
    narrator_default = s.query(Person).filter_by(
        family_id=family_id, user_id=me.id, del_flag=0).first()
    narrator_default_id = narrator_default.id if narrator_default else ""
    if request.method == "POST":
        from models import new_id
        topic = request.form.get("topic", "").strip()
        content = request.form.get("content", "").strip()
        # Quill 空编辑器提交的是 <p><br></p>，视为空
        if content in ("", "<p><br></p>", "<p></p>"):
            content = ""
        # 白名单清洗防 XSS（非法标签去掉，合法排版保留）
        from sanitize import sanitize_html
        content = sanitize_html(content)
        subject_id = request.form.get("subject_id") or None
        narrator_person_id = request.form.get("narrator_person_id") or None
        if narrator_person_id and not any(p.id == narrator_person_id for p in persons):
            narrator_person_id = None
        related_ids = [pid for pid in request.form.getlist("related_ids") if pid]
        p_start = request.form.get("period_start") or None
        p_end = request.form.get("period_end") or None
        precision = request.form.get("period_precision", "day")
        action = request.form.get("action", "draft")
        if not topic or not content:
            return render_template("write.html", family=fam, persons=persons, me=me,
                                   error="标题和正文不能为空",
                                   form=request.form,
                                   members=_family_member_users(s, family_id))
        iv = Interview(
            id=new_id(), family_id=family_id, author_id=me.id,
            person_id=subject_id, topic=topic, status="done",
            publish_status="published" if action == "publish" else "draft",
            narrator_person_id=narrator_person_id or narrator_default_id or None,
            period_start=datetime.date.fromisoformat(p_start) if p_start else None,
            period_end=datetime.date.fromisoformat(p_end) if p_end else None,
            period_precision=precision,
            create_by=me.id, create_date=datetime.datetime.now(),
        )
        s.add(iv)
        s.flush()
        _save_visibility(s, iv, request.form, family_id, me)
        s.add(Draft(id=new_id(), interview_id=iv.id, version=1, is_current=True,
                    content=content, create_by=me.id,
                    create_date=datetime.datetime.now()))
        if subject_id:
            s.add(InterviewPerson(id=new_id(), interview_id=iv.id,
                                  person_id=subject_id, role="subject"))
        for pid in related_ids:
            if pid != subject_id:
                s.add(InterviewPerson(id=new_id(), interview_id=iv.id,
                                      person_id=pid, role="related"))
        s.commit()
        if action == "publish":
            return redirect(url_for("main.story_detail", family_id=family_id,
                                    interview_id=iv.id))
        return redirect(url_for("main.my_drafts", family_id=family_id))
    return render_template("write.html", family=fam, persons=persons, me=me,
                           form=request.form,
                           members=_family_member_users(s, family_id),
                           narrator_default_id=narrator_default_id)


@bp.route("/f/<family_id>/drafts")
def my_drafts(family_id):
    me = _current_user()
    if not me:
        return redirect(url_for("main.login", next=request.path))
    fam = _family_or_404(family_id)
    s = _s()
    rows = s.query(Interview).filter(
        Interview.family_id == family_id, Interview.author_id == me.id,
        Interview.publish_status == "draft", Interview.del_flag == 0)\
        .order_by(Interview.create_date.desc()).all()
    return render_template("drafts.html", family=fam, rows=rows, me=me)


@bp.route("/f/<family_id>/story/<interview_id>/publish", methods=["POST"])
def publish_article(family_id, interview_id):
    me = _current_user()
    if not me:
        return redirect(url_for("main.login", next=request.path))
    _family_or_404(family_id)
    s = _s()
    iv = s.query(Interview).filter_by(id=interview_id, family_id=family_id,
                                      del_flag=0).first()
    if not iv or iv.author_id != me.id:
        abort(404)
    iv.publish_status = "published"
    iv.update_date = datetime.datetime.now()
    s.commit()
    return redirect(url_for("main.story_detail", family_id=family_id,
                            interview_id=interview_id))


# ---------------- 编辑草稿（仅作者，仅草稿可改） ----------------

@bp.route("/f/<family_id>/story/<interview_id>/edit", methods=["GET", "POST"])
def edit_article(family_id, interview_id):
    from sqlalchemy import func
    me = _current_user()
    if not me:
        return redirect(url_for("main.login", next=request.path))
    fam = _family_or_404(family_id)
    s = _s()
    iv = s.query(Interview).filter_by(id=interview_id, family_id=family_id,
                                      del_flag=0).first()
    if not iv or iv.author_id != me.id or (iv.publish_status or "published") != "draft":
        abort(404)
    persons = s.query(Person).filter_by(family_id=family_id, del_flag=0)\
        .order_by(Person.sort).all()
    cur_draft = s.query(Draft).filter_by(interview_id=iv.id, is_current=True,
                                         del_flag=0).first()
    cur_links = s.query(InterviewPerson).filter_by(interview_id=iv.id,
                                                   del_flag=0).all()
    if request.method == "POST":
        from models import new_id
        topic = request.form.get("topic", "").strip()
        content = request.form.get("content", "").strip()
        if content in ("", "<p><br></p>", "<p></p>"):
            content = ""
        from sanitize import sanitize_html
        content = sanitize_html(content)
        subject_id = request.form.get("subject_id") or None
        narrator_person_id = request.form.get("narrator_person_id") or None
        if narrator_person_id and not any(p.id == narrator_person_id for p in persons):
            narrator_person_id = None
        related_ids = [pid for pid in request.form.getlist("related_ids") if pid]
        p_start = request.form.get("period_start") or None
        p_end = request.form.get("period_end") or None
        precision = request.form.get("period_precision", "day")
        action = request.form.get("action", "draft")
        if not topic or not content:
            return render_template("write.html", family=fam, persons=persons, me=me,
                                   error="标题和正文不能为空", form=request.form,
                                   edit_iv=iv,
                                   members=_family_member_users(s, family_id),
                                   cur_visibility=iv.visibility or "public",
                                   cur_viewer_ids={v.user_id for v in s.query(InterviewViewer).filter_by(interview_id=iv.id, del_flag=0).all()},
                                   existing_content=cur_draft.content if cur_draft else "",
                                   related_ids={l.person_id for l in cur_links
                                                if l.role == "related"})
        iv.topic = topic
        iv.person_id = subject_id
        iv.narrator_person_id = narrator_person_id
        iv.period_start = datetime.date.fromisoformat(p_start) if p_start else None
        iv.period_end = datetime.date.fromisoformat(p_end) if p_end else None
        iv.period_precision = precision
        iv.update_date = datetime.datetime.now()
        _save_visibility(s, iv, request.form, family_id, me)
        if action == "publish":
            iv.publish_status = "published"
        # 旧版本保留，写新版本
        if cur_draft:
            cur_draft.is_current = False
        max_v = s.query(func.max(Draft.version)).filter_by(interview_id=iv.id).scalar() or 0
        s.add(Draft(id=new_id(), interview_id=iv.id, version=max_v + 1,
                    is_current=True, content=content, create_by=me.id,
                    create_date=datetime.datetime.now()))
        for l in cur_links:
            l.del_flag = 1
        if subject_id:
            s.add(InterviewPerson(id=new_id(), interview_id=iv.id,
                                  person_id=subject_id, role="subject"))
        for pid in related_ids:
            if pid != subject_id:
                s.add(InterviewPerson(id=new_id(), interview_id=iv.id,
                                      person_id=pid, role="related"))
        s.commit()
        if action == "publish":
            return redirect(url_for("main.story_detail", family_id=family_id,
                                    interview_id=iv.id))
        return redirect(url_for("main.my_drafts", family_id=family_id))
    form_data = {
        "topic": iv.topic or "",
        "subject_id": iv.person_id or "",
        "narrator_person_id": iv.narrator_person_id or "",
        "period_start": iv.period_start.isoformat() if iv.period_start else "",
        "period_end": iv.period_end.isoformat() if iv.period_end else "",
        "period_precision": iv.period_precision or "day",
    }
    narrator_default = s.query(Person).filter_by(
        family_id=family_id, user_id=me.id, del_flag=0).first()
    return render_template("write.html", family=fam, persons=persons, me=me,
                           form=form_data, edit_iv=iv,
                           members=_family_member_users(s, family_id),
                           cur_visibility=iv.visibility or "public",
                           cur_viewer_ids={v.user_id for v in s.query(InterviewViewer).filter_by(interview_id=iv.id, del_flag=0).all()},
                           existing_content=cur_draft.content if cur_draft else "",
                           related_ids={l.person_id for l in cur_links
                                        if l.role == "related"},
                           narrator_default_id=narrator_default.id if narrator_default else "")


# ---------------- 家族树管理（仅家庭管理员 = 创建者） ----------------

def _member_role(family_id, user_id):
    if not user_id:
        return None
    m = _s().query(FamilyMember).filter_by(family_id=family_id, user_id=user_id,
                                            del_flag=0).first()
    if m:
        return m.role
    # 兼容老数据：没有成员记录时，创建者视为 owner
    fam = _s().query(Family).filter_by(id=family_id).first()
    if fam and fam.owner_user_id == user_id:
        return "owner"
    return None


def _is_admin(fam, me):
    """家庭管理员：owner 或 admin。权限按家庭隔离。"""
    return _member_role(fam.id, me.id if me else None) in ("owner", "admin")


def _is_owner(fam, me):
    return _member_role(fam.id, me.id if me else None) == "owner"


def _set_spouse(s, family_id, p, new_spouse_id):
    """设置配偶（双向）；自动处理旧配对的解绑。"""
    if new_spouse_id == p.id:
        new_spouse_id = None
    new_sp = None
    if new_spouse_id:
        new_sp = s.query(Person).filter_by(id=new_spouse_id, family_id=family_id,
                                            del_flag=0).first()
        if not new_sp:
            return "配偶不存在"
    if new_spouse_id != p.spouse_id:
        old = s.query(Person).filter_by(id=p.spouse_id, family_id=family_id).first() \
            if p.spouse_id else None
        if old is not None and old.spouse_id == p.id:
            old.spouse_id = None
        if new_sp and new_sp.spouse_id and new_sp.spouse_id != p.id:
            oo = s.query(Person).filter_by(id=new_sp.spouse_id,
                                           family_id=family_id).first()
            if oo is not None and oo.spouse_id == new_sp.id:
                oo.spouse_id = None
        p.spouse_id = new_spouse_id
        if new_sp:
            new_sp.spouse_id = p.id
    return None


def _next_person_id(family_id):
    s = _s()
    ids = [r[0] for r in s.query(Person.id).filter(
        Person.family_id == family_id, Person.id.like("p%")).all()]
    nums = [int(i[1:]) for i in ids if i[1:].isdigit()]
    return f"p{max(nums) + 1 if nums else 1:02d}"


def _tree_persons(family_id):
    return _s().query(Person).filter_by(family_id=family_id, del_flag=0)\
        .order_by(Person.sort).all()


def _user_map():
    return {u.id: u for u in _s().query(User).filter_by(del_flag=0).all()}


@bp.route("/f/<family_id>/tree/add", methods=["GET", "POST"])
def tree_add(family_id):
    me = _current_user()
    fam = _family_or_404(family_id)
    if not _is_admin(fam, me):
        abort(403)
    s = _s()
    persons = _tree_persons(family_id)
    if request.method == "POST":
        from models import new_id
        name = request.form.get("name", "").strip()
        if not name:
            return render_template("tree_form.html", family=fam, persons=persons,
                                   me=me, error="姓名不能为空", form=request.form,
                                   mode="add")
        parent_id = request.form.get("parent_id") or "0"
        parent = s.query(Person).filter_by(id=parent_id, family_id=family_id,
                                           del_flag=0).first() if parent_id != "0" else None
        if parent_id != "0" and not parent:
            return render_template("tree_form.html", family=fam, persons=persons,
                                   me=me, error="挂靠的上级人物不存在",
                                   form=request.form, mode="add")
        aliases = [a.strip() for a in request.form.get("aliases", "").split("，")
                   if a.strip()] or None
        notes = [n.strip() for n in request.form.get("notes", "").split("，")
                 if n.strip()] or None
        try:
            birth_year = int(request.form.get("birth_year") or 0) or None
            death_year = int(request.form.get("death_year") or 0) or None
            sort = int(request.form.get("sort") or 0)
        except ValueError:
            return render_template("tree_form.html", family=fam, persons=persons,
                                   me=me, error="年份/排序请填数字",
                                   form=request.form, mode="add")
        p = Person(
            id=_next_person_id(family_id), family_id=family_id,
            parent_id=parent.id if parent else "0",
            parent_ids=(parent.parent_ids + parent.id + ",") if parent else "0,",
            name=name, aliases=aliases,
            relation=request.form.get("relation", "").strip() or None,
            birth_year=birth_year, death_year=death_year,
            birth_calendar=_cal(request.form.get("birth_calendar")),
            death_calendar=_cal(request.form.get("death_calendar")),
            alive=bool(request.form.get("alive")),
            status=request.form.get("status") or "pending",
            gender=request.form.get("gender") or None,
            notes=notes, sort=sort,
            create_by=me.id, create_date=datetime.datetime.now(),
        )
        s.add(p)
        s.flush()
        err = _set_spouse(s, family_id, p, request.form.get("spouse_id") or None)
        if err:
            s.rollback()
            return render_template("tree_form.html", family=fam, persons=persons,
                                   me=me, error=err, form=request.form, mode="add")
        s.commit()
        return redirect(url_for("main.family_home", family_id=family_id))
    return render_template("tree_form.html", family=fam, persons=persons, me=me,
                           form=request.form, mode="add")


@bp.route("/f/<family_id>/tree/<person_id>/edit", methods=["GET", "POST"])
def tree_edit(family_id, person_id):
    me = _current_user()
    fam = _family_or_404(family_id)
    if not _is_admin(fam, me):
        abort(403)
    s = _s()
    p = _person_or_404(family_id, person_id)
    persons = [x for x in _tree_persons(family_id) if x.id != p.id]
    users = _s().query(User).filter_by(del_flag=0).all()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            return render_template("tree_form.html", family=fam, persons=persons,
                                   me=me, error="姓名不能为空", form=request.form,
                                   mode="edit", person=p, users=users)
        new_parent_id = request.form.get("parent_id") or "0"
        if new_parent_id != p.parent_id:
            if new_parent_id == p.id:
                return render_template("tree_form.html", family=fam, persons=persons,
                                       me=me, error="不能把自己挂靠到自己名下",
                                       form=request.form, mode="edit", person=p,
                                       users=users)
            new_parent = s.query(Person).filter_by(
                id=new_parent_id, family_id=family_id, del_flag=0).first() \
                if new_parent_id != "0" else None
            if new_parent_id != "0" and not new_parent:
                return render_template("tree_form.html", family=fam, persons=persons,
                                       me=me, error="挂靠的上级人物不存在",
                                       form=request.form, mode="edit", person=p,
                                       users=users)
            # 防环：新上级不能是自己的后代
            if new_parent and new_parent.parent_ids.startswith(
                    (p.parent_ids or "0,") + p.id + ","):
                return render_template("tree_form.html", family=fam, persons=persons,
                                       me=me, error="不能挂靠到自己的后代名下",
                                       form=request.form, mode="edit", person=p,
                                       users=users)
            old_prefix = (p.parent_ids or "0,") + p.id + ","
            new_prefix = (new_parent.parent_ids + new_parent.id + ",") \
                if new_parent else "0,"
            # 子孙的 parent_ids 前缀整体替换
            for desc in s.query(Person).filter(
                    Person.family_id == family_id,
                    Person.parent_ids.like(old_prefix + "%"),
                    Person.del_flag == 0).all():
                desc.parent_ids = new_prefix + desc.parent_ids[len(old_prefix):]
            p.parent_id = new_parent.id if new_parent else "0"
            p.parent_ids = new_prefix
        p.name = name
        p.relation = request.form.get("relation", "").strip() or None
        p.aliases = [a.strip() for a in request.form.get("aliases", "").split("，")
                     if a.strip()] or None
        p.notes = [n.strip() for n in request.form.get("notes", "").split("，")
                   if n.strip()] or None
        try:
            p.birth_year = int(request.form.get("birth_year") or 0) or None
            p.death_year = int(request.form.get("death_year") or 0) or None
            p.birth_calendar = _cal(request.form.get("birth_calendar"))
            p.death_calendar = _cal(request.form.get("death_calendar"))
            p.sort = int(request.form.get("sort") or 0)
        except ValueError:
            s.rollback()
            return render_template("tree_form.html", family=fam, persons=persons,
                                   me=me, error="年份/排序请填数字",
                                   form=request.form, mode="edit", person=p,
                                   users=users)
        p.alive = bool(request.form.get("alive"))
        p.status = request.form.get("status") or p.status
        p.gender = request.form.get("gender") or None
        err = _set_spouse(s, family_id, p, request.form.get("spouse_id") or None)
        if err:
            s.rollback()
            return render_template("tree_form.html", family=fam, persons=persons,
                                   me=me, error=err, form=request.form,
                                   mode="edit", person=p, users=users)
        link_uid = request.form.get("link_user_id") or None
        if link_uid != p.user_id:
            if link_uid:
                conflict = s.query(Person).filter(
                    Person.family_id == family_id, Person.user_id == link_uid,
                    Person.id != p.id, Person.del_flag == 0).first()
                if conflict:
                    s.rollback()
                    return render_template(
                        "tree_form.html", family=fam, persons=persons, me=me,
                        error=f"该账号已关联 {conflict.name}，一人只能关联一个人物",
                        form=request.form, mode="edit", person=p, users=users)
            p.user_id = link_uid
        p.update_by = me.id
        p.update_date = datetime.datetime.now()
        s.commit()
        return redirect(url_for("main.person_page", family_id=family_id,
                                person_id=p.id))
    form_data = {
        "name": p.name, "relation": p.relation or "",
        "aliases": "，".join(p.aliases or []), "notes": "，".join(p.notes or []),
        "birth_year": p.birth_year or "", "death_year": p.death_year or "",
        "birth_calendar": p.birth_calendar or "solar",
        "death_calendar": p.death_calendar or "solar",
        "sort": p.sort or 0, "status": p.status or "pending",
        "parent_id": p.parent_id, "alive": p.alive, "link_user_id": p.user_id or "",
        "gender": p.gender or "", "spouse_id": p.spouse_id or "",
    }
    return render_template("tree_form.html", family=fam, persons=persons, me=me,
                           form=form_data, mode="edit", person=p, users=users)


@bp.route("/f/<family_id>/tree/<person_id>/delete", methods=["POST"])
def tree_delete(family_id, person_id):
    me = _current_user()
    fam = _family_or_404(family_id)
    if not _is_admin(fam, me):
        abort(403)
    s = _s()
    p = _person_or_404(family_id, person_id)
    kids = s.query(Person).filter_by(parent_id=p.id, family_id=family_id,
                                     del_flag=0).count()
    if kids:
        ctx = _person_page_ctx(family_id, p, me)
        ctx["is_admin"] = True
        return render_template("person.html", family=fam, person=p,
                               error=f"「{p.name}」名下还有 {kids} 位人物，请先移动或删除他们",
                               **ctx)
    p.del_flag = 1
    p.update_by = me.id
    p.update_date = datetime.datetime.now()
    s.commit()
    return redirect(url_for("main.family_home", family_id=family_id))


@bp.route("/f/<family_id>/tree/<person_id>/claim", methods=["POST"])
def tree_claim(family_id, person_id):
    """登录用户认领"这是我"：把自己关联到树上的人物。"""
    me = _current_user()
    if not me:
        return redirect(url_for("main.login", next=request.path))
    _family_or_404(family_id)
    s = _s()
    p = _person_or_404(family_id, person_id)
    if p.user_id:
        return redirect(url_for("main.person_page", family_id=family_id,
                                person_id=p.id))
    mine = s.query(Person).filter_by(family_id=family_id, user_id=me.id,
                                     del_flag=0).first()
    if mine:
        ctx = _person_page_ctx(family_id, p, me)
        return render_template("person.html", family=fam, person=p,
                               error=f"你已关联为「{mine.name}」，一人只能关联一个人物",
                               **ctx)
    p.user_id = me.id
    p.update_date = datetime.datetime.now()
    s.commit()
    return redirect(url_for("main.person_page", family_id=family_id,
                            person_id=p.id))


@bp.route("/f/<family_id>/tree/<person_id>/unlink", methods=["POST"])
def tree_unlink(family_id, person_id):
    """解除人物与登录账号的关联：管理员或本人可操作。"""
    me = _current_user()
    if not me:
        return redirect(url_for("main.login", next=request.path))
    fam = _family_or_404(family_id)
    s = _s()
    p = _person_or_404(family_id, person_id)
    if not (p.user_id == me.id or _is_admin(fam, me)):
        abort(403)
    p.user_id = None
    p.update_date = datetime.datetime.now()
    s.commit()
    return redirect(url_for("main.person_page", family_id=family_id,
                            person_id=p.id))


# ---------------- 家庭成员管理（仅创建者 owner） ----------------

@bp.route("/f/<family_id>/members/add", methods=["POST"])
def member_add(family_id):
    me = _current_user()
    fam = _family_or_404(family_id)
    if not _is_owner(fam, me):
        abort(403)
    s = _s()
    user_id = request.form.get("user_id") or None
    role = request.form.get("role") or "member"
    if role not in ("admin", "member"):
        role = "member"
    u = s.query(User).filter_by(id=user_id, del_flag=0).first() if user_id else None
    if not u:
        abort(404)
    from models import new_id
    m = s.query(FamilyMember).filter_by(family_id=family_id, user_id=user_id).first()
    if m:
        m.del_flag = 0
        if m.role != "owner":
            m.role = role
        m.update_by = me.id
        m.update_date = datetime.datetime.now()
    else:
        s.add(FamilyMember(id=new_id(), family_id=family_id, user_id=user_id,
                           role=role, create_by=me.id,
                           create_date=datetime.datetime.now()))
    s.commit()
    return redirect(url_for("main.family_home", family_id=family_id))


@bp.route("/f/<family_id>/members/<member_id>/remove", methods=["POST"])
def member_remove(family_id, member_id):
    me = _current_user()
    fam = _family_or_404(family_id)
    if not _is_owner(fam, me):
        abort(403)
    s = _s()
    m = s.query(FamilyMember).filter_by(id=member_id, family_id=family_id,
                                        del_flag=0).first()
    if not m:
        abort(404)
    if m.role == "owner":
        abort(400, "不能移除创建者")
    if m.user_id == me.id:
        abort(400, "不能移除自己")
    m.del_flag = 1
    m.update_by = me.id
    m.update_date = datetime.datetime.now()
    s.commit()
    return redirect(url_for("main.family_home", family_id=family_id))


# ---------------- 人物小传编辑（管理员；版本化） ----------------

@bp.route("/f/<family_id>/person/<person_id>/portrait/edit", methods=["GET", "POST"])
def portrait_edit(family_id, person_id):
    from sqlalchemy import func
    me = _current_user()
    fam = _family_or_404(family_id)
    if not _is_admin(fam, me):
        abort(403)
    p = _person_or_404(family_id, person_id)
    s = _s()
    cur = s.query(Portrait).filter_by(person_id=person_id, del_flag=0)\
        .order_by(Portrait.version.desc()).first()
    if request.method == "POST":
        from models import new_id
        text = request.form.get("profile_text", "").strip()
        if not text:
            return render_template("portrait_form.html", family=fam, person=p,
                                   me=me, error="小传内容不能为空",
                                   text=request.form.get("profile_text", ""),
                                   version=cur.version if cur else 0)
        max_v = s.query(func.max(Portrait.version))\
            .filter_by(person_id=person_id).scalar() or 0
        s.add(Portrait(id=new_id(), person_id=person_id, version=max_v + 1,
                       profile_text=text, create_by=me.id,
                       create_date=datetime.datetime.now()))
        s.commit()
        return redirect(url_for("main.person_page", family_id=family_id,
                                person_id=person_id))
    return render_template("portrait_form.html", family=fam, person=p, me=me,
                           text=cur.profile_text if cur else "",
                           version=cur.version if cur else 0)


# ---------------- 照片上传（登录用户；描述必填） ----------------

ALLOWED_IMG = {"jpg", "jpeg", "png", "gif", "webp"}
MAX_IMG = 10 * 1024 * 1024


@bp.route("/uploads/<path:filename>")
def uploaded_file(filename):
    """本地后端的文件服务；OSS 后端走签名 URL，不经过这里。"""
    from config import Config
    from flask import send_from_directory
    return send_from_directory(Config.UPLOAD_DIR, filename)


@bp.route("/f/<family_id>/person/<person_id>/photos/upload", methods=["POST"])
def photo_upload(family_id, person_id):
    me = _current_user()
    if not me:
        return redirect(url_for("main.login", next=request.path))
    fam = _family_or_404(family_id)
    p = _person_or_404(family_id, person_id)
    s = _s()

    def fail(msg):
        ctx = _person_page_ctx(family_id, p, me)
        return render_template("person.html", family=fam, person=p,
                               error=msg, **ctx)

    f = request.files.get("photo") or request.files.get("photo2")
    caption = request.form.get("caption", "").strip()
    if not f or not f.filename:
        return fail("请选择照片")
    if not caption:
        return fail("请填写照片描述")
    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    if ext not in ALLOWED_IMG:
        return fail("只支持 jpg / png / gif / webp 格式")
    data = f.read()
    if len(data) > MAX_IMG:
        return fail("照片太大，请传 10MB 以内的")
    # 文件头魔数校验（扩展名可伪造）
    if not (data[:8] == b"\x89PNG\r\n\x1a\n" or data[:3] == b"\xff\xd8\xff"
            or data[:6] in (b"GIF87a", b"GIF89a")
            or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")):
        return fail("文件不是有效图片，请重新选择")
    try:
        photo_year = int(request.form.get("photo_year") or 0) or None
    except ValueError:
        return fail("年份请填数字")
    import uuid
    from storage import get_storage
    key = f"{family_id}/{person_id}/{uuid.uuid4().hex}.{ext}"
    try:
        rel = get_storage().save(data, key)
    except RuntimeError as e:
        return fail(str(e))
    from models import new_id
    s.add(Photo(id=new_id(), family_id=family_id, person_id=person_id,
                photo_year=photo_year, storage_path=rel, caption=caption,
                uploaded_by=me.id, create_by=me.id,
                create_date=datetime.datetime.now()))
    s.commit()
    return redirect(url_for("main.person_page", family_id=family_id,
                            person_id=person_id))


@bp.route("/f/<family_id>/person/<person_id>/photos/<photo_id>/delete",
          methods=["POST"])
def photo_delete(family_id, person_id, photo_id):
    """删除照片：上传者本人或管理员可操作；存储对象一并删除。"""
    me = _current_user()
    if not me:
        return redirect(url_for("main.login", next=request.path))
    fam = _family_or_404(family_id)
    _person_or_404(family_id, person_id)
    s = _s()
    ph = s.query(Photo).filter_by(id=photo_id, person_id=person_id,
                                  del_flag=0).first()
    if not ph:
        abort(404)
    if ph.uploaded_by != me.id and not _is_admin(fam, me):
        abort(403)
    if ph.storage_path:
        from storage import get_storage
        try:
            get_storage().delete(ph.storage_path)
        except Exception:
            pass  # 文件已不在也继续删记录
    ph.del_flag = 1
    ph.update_by = me.id
    ph.update_date = datetime.datetime.now()
    s.commit()
    return redirect(url_for("main.person_page", family_id=family_id,
                            person_id=person_id))


@bp.route("/f/<family_id>/story/<interview_id>/comments/<comment_id>/delete",
          methods=["POST"])
def comment_delete(family_id, interview_id, comment_id):
    """删除评论：作者本人或管理员可操作；软删占位，子评论保留。"""
    me = _current_user()
    if not me:
        return redirect(url_for("main.login", next=request.path))
    fam = _family_or_404(family_id)
    s = _s()
    iv = s.query(Interview).filter_by(id=interview_id, family_id=family_id,
                                      del_flag=0).first()
    if not iv or not _can_view(iv, me):
        abort(404)
    c = s.query(Comment).filter_by(id=comment_id, interview_id=interview_id,
                                   del_flag=0).first()
    if not c:
        abort(404)
    if c.user_id != me.id and not _is_admin(fam, me):
        abort(403)
    c.content = "（该评论已删除）"
    c.update_by = me.id
    c.update_date = datetime.datetime.now()
    s.commit()
    return redirect(url_for("main.story_detail", family_id=family_id,
                            interview_id=interview_id))


# ---------------- 时间轴事件管理（管理员） ----------------

@bp.route("/f/<family_id>/person/<person_id>/timeline/add", methods=["GET", "POST"])
def timeline_add(family_id, person_id):
    me = _current_user()
    fam = _family_or_404(family_id)
    if not _is_admin(fam, me):
        abort(403)
    p = _person_or_404(family_id, person_id)
    s = _s()
    if request.method == "POST":
        from models import new_id
        title = request.form.get("title", "").strip()
        if not title:
            return render_template("timeline_form.html", family=fam, person=p,
                                   me=me, error="事件标题不能为空",
                                   form=request.form, mode="add")
        date_s = request.form.get("event_date") or None
        try:
            event_date = datetime.date.fromisoformat(date_s) if date_s else None
        except ValueError:
            return render_template("timeline_form.html", family=fam, person=p,
                                   me=me, error="日期格式不对",
                                   form=request.form, mode="add")
        s.add(TimelineEvent(
            id=new_id(), family_id=family_id, person_id=person_id,
            event_date=event_date,
            date_precision=request.form.get("date_precision") or "day",
            title=title,
            description=request.form.get("description", "").strip() or None,
            create_by=me.id, create_date=datetime.datetime.now()))
        s.commit()
        return redirect(url_for("main.person_page", family_id=family_id,
                                person_id=person_id))
    return render_template("timeline_form.html", family=fam, person=p, me=me,
                           form=request.form, mode="add")


@bp.route("/f/<family_id>/person/<person_id>/timeline/<event_id>/edit",
          methods=["GET", "POST"])
def timeline_edit(family_id, person_id, event_id):
    me = _current_user()
    fam = _family_or_404(family_id)
    if not _is_admin(fam, me):
        abort(403)
    p = _person_or_404(family_id, person_id)
    s = _s()
    e = s.query(TimelineEvent).filter_by(id=event_id, person_id=person_id,
                                         del_flag=0).first()
    if not e:
        abort(404)
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        if not title:
            return render_template("timeline_form.html", family=fam, person=p,
                                   me=me, error="事件标题不能为空",
                                   form=request.form, mode="edit", event=e)
        date_s = request.form.get("event_date") or None
        try:
            e.event_date = datetime.date.fromisoformat(date_s) if date_s else None
        except ValueError:
            return render_template("timeline_form.html", family=fam, person=p,
                                   me=me, error="日期格式不对",
                                   form=request.form, mode="edit", event=e)
        e.title = title
        e.date_precision = request.form.get("date_precision") or "day"
        e.description = request.form.get("description", "").strip() or None
        e.update_by = me.id
        e.update_date = datetime.datetime.now()
        s.commit()
        return redirect(url_for("main.person_page", family_id=family_id,
                                person_id=person_id))
    form_data = {
        "title": e.title or "",
        "event_date": e.event_date.isoformat() if e.event_date else "",
        "date_precision": e.date_precision or "day",
        "description": e.description or "",
    }
    return render_template("timeline_form.html", family=fam, person=p, me=me,
                           form=form_data, mode="edit", event=e)


@bp.route("/f/<family_id>/person/<person_id>/timeline/<event_id>/delete",
          methods=["POST"])
def timeline_delete(family_id, person_id, event_id):
    me = _current_user()
    fam = _family_or_404(family_id)
    if not _is_admin(fam, me):
        abort(403)
    _person_or_404(family_id, person_id)
    s = _s()
    e = s.query(TimelineEvent).filter_by(id=event_id, person_id=person_id,
                                         del_flag=0).first()
    if not e:
        abort(404)
    e.del_flag = 1
    e.update_by = me.id
    e.update_date = datetime.datetime.now()
    s.commit()
    return redirect(url_for("main.person_page", family_id=family_id,
                            person_id=person_id))


@bp.route("/guide")
def guide():
    return render_template("guide.html", me=_current_user())


# ---------------- sync-json 同步入库（管理员） ----------------

@bp.route("/f/<family_id>/sync", methods=["GET", "POST"])
def sync_import(family_id):
    """同步入库页：粘贴 skill 输出的 sync-json → 校验 → 入库（方式 A）。"""
    me = _current_user()
    fam = _family_or_404(family_id)
    if not _is_admin(fam, me):
        abort(403)
    from sync_engine import SyncError, apply_sync, log_sync_failure
    s = _s()
    result = None
    if request.method == "POST":
        raw = request.form.get("sync_json", "").strip()
        # 兼容直接粘贴 ```sync-json ... ``` 代码块
        m = re.search(r"```sync-json\s*(\{.*?\})\s*```", raw, re.S)
        if m:
            raw = m.group(1)
        try:
            packet = json.loads(raw)
        except Exception:
            result = (False, "JSON 解析失败，请检查格式（可直接粘贴 ```sync-json 代码块）")
        else:
            try:
                result = apply_sync(s, family_id, packet, me.id)
            except SyncError as e:
                log_sync_failure(s, family_id, packet, me.id, str(e))
                result = (False, str(e))
    logs = s.query(SyncLog).filter_by(family_id=family_id)\
        .order_by(SyncLog.create_date.desc()).limit(20).all()
    return render_template("sync.html", family=fam, me=me, result=result,
                           logs=logs)


@bp.route("/api/sync", methods=["POST"])
def api_sync():
    """入库接口（给将来 MCP/小程序用）：需管理员登录，JSON body 含 family_id + packet。"""
    me = _current_user()
    if not me:
        return jsonify({"ok": False, "error": "need_login"}), 401
    data = request.get_json(force=True, silent=True) or {}
    fam = _family_or_404(data.get("family_id"))
    if not _is_admin(fam, me):
        return jsonify({"ok": False, "error": "forbidden"}), 403
    from sync_engine import SyncError, apply_sync, log_sync_failure
    s = _s()
    packet = data.get("packet") or data
    try:
        ok, summary = apply_sync(s, fam.id, packet, me.id)
        return jsonify({"ok": True, "applied": ok, "summary": summary})
    except SyncError as e:
        log_sync_failure(s, fam.id, packet if isinstance(packet, dict) else {},
                         me.id, str(e))
        return jsonify({"ok": False, "error": str(e)}), 400


# ---------------- 创建家庭（登录用户） ----------------

@bp.route("/families/new", methods=["GET", "POST"])
def family_new():
    me = _current_user()
    if not me:
        return redirect(url_for("main.login", next=request.path))
    s = _s()
    error = None
    if request.method == "POST":
        from models import new_id
        import re as _re
        name = request.form.get("name", "").strip()
        fid = request.form.get("family_id", "").strip().lower()
        if not name:
            error = "请填写家庭名称"
        elif fid and not _re.fullmatch(r"[a-z0-9][a-z0-9\-]{1,30}", fid):
            error = "家庭代号只能用小写字母、数字和短横线（3~31 位）"
        elif fid and s.query(Family).filter_by(id=fid, del_flag=0).first():
            error = f"代号 {fid} 已被占用，换一个试试"
        else:
            fid = fid or new_id()[:8]
            while s.query(Family).filter_by(id=fid).first():
                fid = new_id()[:8]
            fam = Family(id=fid, name=name[:64], owner_user_id=me.id,
                         create_by=me.id, create_date=datetime.datetime.now())
            s.add(fam)
            s.add(FamilyMember(id=new_id(), family_id=fid, user_id=me.id,
                               role="owner", create_by=me.id,
                               create_date=datetime.datetime.now()))
            s.commit()
            return redirect(url_for("main.family_home", family_id=fid))
    return render_template("family_form.html", me=me, error=error,
                           form=request.form)


# ---------------- 管理员为家人开通账号 ----------------

@bp.route("/f/<family_id>/members/create-account", methods=["POST"])
def member_create_account(family_id):
    """管理员为家人开通登录账号：手机号或用户名 + 密码（老人可由子女代建）。"""
    me = _current_user()
    fam = _family_or_404(family_id)
    if not _is_admin(fam, me):
        abort(403)
    import re as _re
    s = _s()
    nickname = request.form.get("nickname", "").strip()
    login_type = request.form.get("login_type", "phone")
    login_id = request.form.get("login_id", "").strip()
    password = request.form.get("password", "")
    error = None
    if not nickname:
        error = "请填写家人昵称（如：爷爷）"
    elif len(password) < 6:
        error = "密码至少 6 位"
    elif login_type == "phone":
        if not _re.fullmatch(r"\d{11}", login_id):
            error = "手机号应为 11 位数字"
        elif s.query(User).filter_by(phone=login_id, del_flag=0).first():
            error = "该手机号已注册"
    elif login_type == "username":
        if not _re.fullmatch(r"[a-zA-Z0-9_]{3,20}", login_id):
            error = "用户名为 3~20 位字母/数字/下划线"
        elif s.query(User).filter_by(username=login_id, del_flag=0).first():
            error = "该用户名已被占用"
    else:
        error = "登录方式不对"
    if error:
        session["member_form_error"] = error
        return redirect(url_for("main.family_home", family_id=family_id))
    from models import new_id
    u = User(id=new_id(), nickname=nickname,
             phone=login_id if login_type == "phone" else None,
             username=login_id if login_type == "username" else None,
             password_hash=generate_password_hash(password),
             create_by=me.id, create_date=datetime.datetime.now())
    s.add(u)
    s.flush()
    s.add(FamilyMember(id=new_id(), family_id=family_id, user_id=u.id,
                       role="member", create_by=me.id,
                       create_date=datetime.datetime.now()))
    s.commit()
    # 密码只存 hash，这里一次性展示给管理员转告家人
    session["created_account"] = {"nickname": nickname, "login": login_id,
                                  "password": password}
    return redirect(url_for("main.family_home", family_id=family_id))


# ---------------- 管理员重置成员密码 ----------------

@bp.route("/f/<family_id>/members/<member_id>/reset-password", methods=["POST"])
def member_reset_password(family_id, member_id):
    """忘记密码找管理员重置：创建者可重置所有人，管理员只能重置普通成员。"""
    me = _current_user()
    fam = _family_or_404(family_id)
    if not _is_admin(fam, me):
        abort(403)
    s = _s()
    m = s.query(FamilyMember).filter_by(id=member_id, family_id=family_id,
                                        del_flag=0).first()
    if not m:
        abort(404)
    u = s.query(User).filter_by(id=m.user_id, del_flag=0).first()
    if not u:
        abort(404)
    is_owner = _is_owner(fam, me)
    if not is_owner and m.role != "member":
        abort(403)  # 管理员不能重置创建者/其他管理员的密码
    new_password = request.form.get("new_password", "")
    if len(new_password) < 6:
        session["member_form_error"] = "新密码至少 6 位"
        return redirect(url_for("main.family_home", family_id=family_id))
    u.password_hash = generate_password_hash(new_password)
    u.update_by = me.id
    u.update_date = datetime.datetime.now()
    s.commit()
    session["reset_notice"] = {
        "nickname": u.nickname or u.phone or u.username,
        "login": u.phone or u.username or "",
        "password": new_password}
    return redirect(url_for("main.family_home", family_id=family_id))


# ---------------- AI 问答 & 周报导读 ----------------

@bp.route("/f/<family_id>/ask", methods=["GET", "POST"])
def ai_ask(family_id):
    """AI 问答：家庭知识库 + 用户记忆，需登录。"""
    me = _current_user()
    if not me:
        return redirect(url_for("main.login", next=request.path))
    fam = _family_or_404(family_id)
    import ai as ai_mod
    s = _s()
    error = None
    if request.method == "POST":
        msg = request.form.get("message", "").strip()
        if not msg:
            error = "请输入问题"
        elif not ai_mod.ai_enabled():
            error = "AI 未启用：请联系管理员配置 DEEPSEEK_API_KEY"
        else:
            try:
                ai_mod.chat(family_id, me.id, msg, family_name=fam.name)
            except ai_mod.AIError as e:
                error = str(e)
        return redirect(url_for("main.ai_ask", family_id=family_id,
                                error=error) if error else
                        url_for("main.ai_ask", family_id=family_id))
    msgs = s.query(ai_mod.AiMessage).filter_by(
        family_id=family_id, user_id=me.id, del_flag=0).order_by(
        ai_mod.AiMessage.create_date.desc()).limit(30).all()
    return render_template("ask.html", family=fam, me=me,
                           msgs=list(reversed(msgs)),
                           ai_enabled=ai_mod.ai_enabled(),
                           error=request.args.get("error"))


@bp.route("/f/<family_id>/weekly/<int:week>/ai-summary", methods=["POST"])
def ai_weekly_summary(family_id, week):
    """生成本周 AI 导读（管理员，结果按周缓存）。"""
    me = _current_user()
    fam = _family_or_404(family_id)
    if not _is_admin(fam, me):
        abort(403)
    import ai as ai_mod
    if not ai_mod.ai_enabled():
        abort(400, "AI 未启用：请配置 DEEPSEEK_API_KEY")
    try:
        ai_mod.summarize_weekly(family_id, week,
                                _weekly_report_json(family_id, week),
                                force=True, user_id=me.id)
    except ai_mod.AIError as e:
        return render_template("weekly.html", family=fam, week=week,
                               **_weekly_data(family_id, week, viewer_id=me.id),
                               ai_summary=None, ai_enabled=True,
                               is_admin=True, ai_error=str(e))
    return redirect(url_for("main.weekly_report", family_id=family_id,
                            week=week))


# ---------------- 写作/采访计划 ----------------

def _plan_or_404(family_id, plan_id):
    s = _s()
    p = s.query(WritingPlan).filter_by(
        id=plan_id, family_id=family_id, del_flag=0).first()
    if not p:
        abort(404)
    return p


def _plan_items(plan):
    try:
        items = json.loads(plan.items or "[]")
    except ValueError:
        items = []
    return items if isinstance(items, list) else []


@bp.route("/f/<family_id>/plans")
def plan_list(family_id):
    me = _current_user()
    if not me:
        return redirect(url_for("main.login", next=request.path))
    fam = _family_or_404(family_id)
    s = _s()
    plans = s.query(WritingPlan).filter_by(
        family_id=family_id, del_flag=0).order_by(
        WritingPlan.create_date.desc()).all()
    viewer = s.query(Person).filter_by(
        family_id=family_id, user_id=me.id, del_flag=0).first() \
        if me else None
    import ai as ai_mod
    return render_template("plans.html", family=fam, me=me, plans=plans,
                           plan_items=_plan_items,
                           is_admin=_is_admin(fam, me),
                           viewer_person_id=viewer.id if viewer else None,
                           ai_enabled=ai_mod.ai_enabled())


@bp.route("/f/<family_id>/plans/new")
def plan_new(family_id):
    me = _current_user()
    fam = _family_or_404(family_id)
    if not _is_admin(fam, me):
        abort(403)
    s = _s()
    persons = s.query(Person).filter_by(
        family_id=family_id, del_flag=0).order_by(Person.sort).all()
    suggestion = session.pop("plan_suggestion", None)
    import ai as ai_mod
    rows = []
    if suggestion:
        for it in suggestion.get("items", []):
            rows.append({"person_id": it.get("person_id", ""),
                         "note": it.get("reason", ""), "status": "pending"})
    while len(rows) < 10:
        rows.append({"person_id": "", "note": "", "status": "pending"})
    return render_template("plan_form.html", family=fam, me=me, plan=None,
                           persons=persons, rows=rows,
                           suggested_title=suggestion.get("title", "")
                           if suggestion else "",
                           ai_enabled=ai_mod.ai_enabled(), error=None)


@bp.route("/f/<family_id>/plans/ai-suggest", methods=["POST"])
def plan_ai_suggest(family_id):
    me = _current_user()
    fam = _family_or_404(family_id)
    if not _is_admin(fam, me):
        abort(403)
    import ai as ai_mod
    try:
        suggestion = ai_mod.suggest_writing_plan(
            family_id, family_name=fam.name, user_id=me.id)
    except ai_mod.AIError as e:
        s = _s()
        persons = s.query(Person).filter_by(
            family_id=family_id, del_flag=0).order_by(Person.sort).all()
        rows = [{"person_id": "", "note": "", "status": "pending"}] * 10
        return render_template("plan_form.html", family=fam, me=me, plan=None,
                               persons=persons, rows=rows, suggested_title="",
                               ai_enabled=ai_mod.ai_enabled(), error=str(e))
    session["plan_suggestion"] = suggestion
    return redirect(url_for("main.plan_new", family_id=family_id))


def _save_plan_from_form(plan, title, name_map):
    items = []
    pids = request.form.getlist("person_id")
    notes = request.form.getlist("note")
    statuses = request.form.getlist("item_status")
    for i, pid in enumerate(pids):
        pid = (pid or "").strip()
        if not pid:
            continue
        items.append({"person_id": pid,
                      "person_name": name_map.get(pid, pid),
                      "order": len(items) + 1,
                      "status": statuses[i] if i < len(statuses)
                      and statuses[i] in ("pending", "doing", "done")
                      else "pending",
                      "note": notes[i].strip() if i < len(notes) else ""})
    plan.title = title.strip()[:128]
    plan.items = json.dumps(items, ensure_ascii=False)


def _person_name_map(family_id):
    s = _s()
    return {p.id: p.name for p in s.query(Person).filter_by(
        family_id=family_id, del_flag=0).all()}


@bp.route("/f/<family_id>/plans/create", methods=["POST"])
def plan_create(family_id):
    me = _current_user()
    fam = _family_or_404(family_id)
    if not _is_admin(fam, me):
        abort(403)
    from models import new_id
    s = _s()
    title = request.form.get("title", "").strip()
    if not title:
        persons = s.query(Person).filter_by(
            family_id=family_id, del_flag=0).order_by(Person.sort).all()
        import ai as ai_mod
        rows = [{"person_id": "", "note": "", "status": "pending"}] * 10
        return render_template("plan_form.html", family=fam, me=me, plan=None,
                               persons=persons, rows=rows, suggested_title="",
                               ai_enabled=ai_mod.ai_enabled(),
                               error="请填写计划标题")
    plan = WritingPlan(id=new_id(), family_id=family_id, status="draft",
                       create_by=me.id, create_date=datetime.datetime.now())
    _save_plan_from_form(plan, title, _person_name_map(family_id))
    s.add(plan)
    s.commit()
    return redirect(url_for("main.plan_list", family_id=family_id))


@bp.route("/f/<family_id>/plans/<plan_id>/edit")
def plan_edit(family_id, plan_id):
    me = _current_user()
    fam = _family_or_404(family_id)
    if not _is_admin(fam, me):
        abort(403)
    plan = _plan_or_404(family_id, plan_id)
    s = _s()
    persons = s.query(Person).filter_by(
        family_id=family_id, del_flag=0).order_by(Person.sort).all()
    import ai as ai_mod
    rows = [{"person_id": it.get("person_id", ""),
             "note": it.get("note", ""),
             "status": it.get("status", "pending")}
            for it in _plan_items(plan)]
    while len(rows) < 10:
        rows.append({"person_id": "", "note": "", "status": "pending"})
    return render_template("plan_form.html", family=fam, me=me, plan=plan,
                           persons=persons, rows=rows, suggested_title="",
                           ai_enabled=ai_mod.ai_enabled(),
                           error=None)


@bp.route("/f/<family_id>/plans/<plan_id>/update", methods=["POST"])
def plan_update(family_id, plan_id):
    me = _current_user()
    fam = _family_or_404(family_id)
    if not _is_admin(fam, me):
        abort(403)
    plan = _plan_or_404(family_id, plan_id)
    s = _s()
    title = request.form.get("title", "").strip()
    if not title:
        persons = s.query(Person).filter_by(
            family_id=family_id, del_flag=0).order_by(Person.sort).all()
        import ai as ai_mod
        rows = [{"person_id": it.get("person_id", ""),
                 "note": it.get("note", ""),
                 "status": it.get("status", "pending")}
                for it in _plan_items(plan)]
        while len(rows) < 10:
            rows.append({"person_id": "", "note": "", "status": "pending"})
        return render_template("plan_form.html", family=fam, me=me, plan=plan,
                               persons=persons, rows=rows, suggested_title="",
                               ai_enabled=ai_mod.ai_enabled(),
                               error="请填写计划标题")
    _save_plan_from_form(plan, title, _person_name_map(family_id))
    plan.update_by = me.id
    plan.update_date = datetime.datetime.now()
    s.commit()
    return redirect(url_for("main.plan_list", family_id=family_id))


@bp.route("/f/<family_id>/plans/<plan_id>/activate", methods=["POST"])
def plan_activate(family_id, plan_id):
    me = _current_user()
    fam = _family_or_404(family_id)
    if not _is_admin(fam, me):
        abort(403)
    s = _s()
    plan = _plan_or_404(family_id, plan_id)
    for p in s.query(WritingPlan).filter_by(
            family_id=family_id, status="active", del_flag=0).all():
        p.status = "draft"
    plan.status = "active"
    plan.update_by = me.id
    plan.update_date = datetime.datetime.now()
    s.commit()
    return redirect(url_for("main.plan_list", family_id=family_id))


@bp.route("/f/<family_id>/plans/<plan_id>/archive", methods=["POST"])
def plan_archive(family_id, plan_id):
    me = _current_user()
    fam = _family_or_404(family_id)
    if not _is_admin(fam, me):
        abort(403)
    s = _s()
    plan = _plan_or_404(family_id, plan_id)
    plan.status = "archived"
    plan.update_by = me.id
    plan.update_date = datetime.datetime.now()
    s.commit()
    return redirect(url_for("main.plan_list", family_id=family_id))


@bp.route("/api/writing-plan")
def api_writing_plan():
    """当前写作计划（供 skill 拉取）：开放接口，只返回当前计划。"""
    family_id = request.args.get("family_id", "")
    _family_or_404(family_id)
    s = _s()
    plan = s.query(WritingPlan).filter_by(
        family_id=family_id, status="active", del_flag=0).order_by(
        WritingPlan.update_date.desc()).first()
    if not plan:
        return jsonify({"family_id": family_id, "plan": None})
    return jsonify({"family_id": family_id,
                    "plan": {"id": plan.id, "title": plan.title,
                             "updated": plan.update_date.isoformat()
                             if plan.update_date else None,
                             "items": _plan_items(plan)}})


# ---------------- 短信验证码 / 忘记密码 / 邀请 ----------------

@bp.route("/api/sms-code", methods=["POST"])
def api_sms_code():
    """发送短信验证码：{phone, purpose=register|reset}。"""
    import sms as sms_mod
    data = request.get_json(silent=True) or {}
    phone = (data.get("phone") or "").strip()
    purpose = data.get("purpose") or "register"
    s = _s()
    if purpose == "register":
        if s.query(User).filter_by(phone=phone, del_flag=0).first():
            return jsonify({"ok": False, "error": "该手机号已注册，请直接登录"}), 400
    elif purpose == "reset":
        if not s.query(User).filter_by(phone=phone, del_flag=0).first():
            return jsonify({"ok": False, "error": "该手机号未注册"}), 400
    else:
        return jsonify({"ok": False, "error": "用途不对"}), 400
    try:
        ret = sms_mod.send_code(phone, purpose)
    except sms_mod.SMSError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    out = {"ok": True, "dev_mode": ret["dev_mode"]}
    if ret["dev_mode"]:
        out["dev_code"] = ret["code"]  # 仅开发模式返回，方便原型测试
    return jsonify(out)


@bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """短信自助找回密码：owner 忘密码也不用找人了。"""
    import sms as sms_mod
    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        code = request.form.get("code", "").strip()
        password = request.form.get("password", "")
        s = _s()
        u = s.query(User).filter_by(phone=phone, del_flag=0).first()
        if not u:
            return render_template("forgot.html", error="该手机号未注册")
        if len(password) < 6:
            return render_template("forgot.html", error="新密码至少 6 位")
        try:
            sms_mod.verify_code(phone, code, "reset")
        except sms_mod.SMSError as e:
            return render_template("forgot.html", error=str(e))
        u.password_hash = generate_password_hash(password)
        u.update_date = datetime.datetime.now()
        s.commit()
        session["user_id"] = u.id
        return redirect(url_for("main.index"))
    import sms as sms_mod2
    return render_template("forgot.html",
                           sms_enabled=sms_mod2.sms_enabled())


def _join_family(s, family_id, user_id, me_id):
    """用户加入家庭（幂等）。"""
    from models import new_id
    m = s.query(FamilyMember).filter_by(
        family_id=family_id, user_id=user_id).first()
    now = datetime.datetime.now()
    if m:
        if m.del_flag:
            m.del_flag = 0
            m.update_by = me_id
            m.update_date = now
    else:
        s.add(FamilyMember(id=new_id(), family_id=family_id, user_id=user_id,
                           role="member", create_by=me_id, create_date=now))
    s.commit()


@bp.route("/f/<family_id>/invites/create", methods=["POST"])
def invite_create(family_id):
    """管理员生成邀请码（可设置有效天数/使用次数）。"""
    me = _current_user()
    fam = _family_or_404(family_id)
    if not _is_admin(fam, me):
        abort(403)
    import secrets as _secrets
    from models import new_id
    s = _s()
    days = request.form.get("days", "7").strip()
    max_uses = request.form.get("max_uses", "0").strip()
    try:
        days = max(1, min(365, int(days)))
        max_uses = max(0, int(max_uses))
    except ValueError:
        days, max_uses = 7, 0
    code = _secrets.token_urlsafe(6)[:8]
    while s.query(Invite).filter_by(code=code).first():
        code = _secrets.token_urlsafe(6)[:8]
    now = datetime.datetime.now()
    inv = Invite(id=new_id(), family_id=family_id, code=code,
                 max_uses=max_uses, used_count=0,
                 expire_at=now + datetime.timedelta(days=days),
                 create_by=me.id, create_date=now)
    s.add(inv)
    s.commit()
    session["new_invite"] = {"code": code,
                             "url": url_for("main.join_by_invite", code=code,
                                            _external=True)}
    return redirect(url_for("main.family_home", family_id=family_id))


def _valid_invite(code):
    s = _s()
    inv = s.query(Invite).filter_by(code=code, del_flag=0).first()
    if not inv:
        return None
    now = datetime.datetime.now()
    if inv.expire_at and inv.expire_at < now:
        return None
    if inv.max_uses and inv.used_count >= inv.max_uses:
        return None
    return inv


@bp.route("/join/<code>")
def join_by_invite(code):
    """邀请链接：登录后自动入家庭；未登录先去注册（带邀请码）。"""
    inv = _valid_invite(code)
    if not inv:
        return render_template("join.html", invite=None)
    me = _current_user()
    s = _s()
    fam = s.query(Family).filter_by(id=inv.family_id, del_flag=0).first()
    if me:
        _join_family(s, inv.family_id, me.id, me.id)
        inv.used_count = (inv.used_count or 0) + 1
        s.commit()
        return redirect(url_for("main.family_home", family_id=inv.family_id))
    return render_template("join.html", invite=inv, family=fam)
