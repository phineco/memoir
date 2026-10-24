"""sync-json 入库引擎：把 skill 输出的数据包写入本站 DB。

数据包格式见 memoir-sync-design.md（网站侧实现补充见文末注释）。

匹配原则（诚实优先）：
- 人物只按「映射表 skill_id → person_id」或「姓名精确匹配」对应，对不上绝不硬挂；
- tree_upsert 只更新已有人物的信息字段，不自动改挂靠结构；
  对不上的人一律记入 new_persons（🆕 待定是否入树），由管理员手动入树；
- 所有写操作幂等：client_id 已入库则整包跳过。
"""
import datetime
import re

from models import (Draft, Interview, InterviewPerson, NewPerson, Person,
                    PersonIdMap, Quote, SyncLog, TimelineEvent,
                    VerificationItem, WritingPlan, new_id)
from sqlalchemy.exc import SQLAlchemyError

SUPPORTED = ("tree_upsert", "interview_upsert", "verification_update",
             "new_person", "person_status", "revision_sync", "plan_progress")


class SyncError(Exception):
    pass


def sanitize_html(content, family_id):
    from album import clean_story_images
    from werkzeug.exceptions import BadRequest
    try:
        return clean_story_images(content, family_id)
    except BadRequest as exc:
        raise SyncError(exc.description) from None


def _resolve_person(s, family_id, skill_id=None, name=None, site_id=None):
    """skill 人物 → 本站 Person：先查映射表，再姓名精确匹配，再别名匹配。"""
    for identifier in (skill_id, site_id):
        if identifier is not None and (not isinstance(identifier, str) or len(identifier) > 64):
            raise SyncError("人物 ID 必须为不超过 64 字符的字符串，不能把网站 ID 与 skill ID 混用")
    site_person = None
    if site_id:
        site_person = s.query(Person).filter_by(id=site_id, family_id=family_id, del_flag=0).first()
        if not site_person:
            raise SyncError("网站人物不存在或不属于本家庭，请重新核对 site_person_id")
    if skill_id:
        m = s.query(PersonIdMap).filter_by(
            family_id=family_id, skill_id=skill_id).first()
        if m:
            p = s.query(Person).filter_by(id=m.person_id, family_id=family_id, del_flag=0).first()
            if p:
                if site_person and site_person.id != p.id:
                    raise SyncError("skill ID 已绑定另一人物，不能重新分配，请人工核对")
                return p
            raise SyncError("skill ID 对应人物已不可用，不能复用该 ID，请人工核对")
    if site_person:
        return site_person
    if name:
        candidates = [p for p in s.query(Person).filter_by(
            family_id=family_id, del_flag=0).all()
            if p.name == name or name in (p.aliases or [])]
        if len(candidates) > 1:
            raise SyncError("姓名或别名对应多个人物，请核对网站人物 ID，使用 site_person_id 明确身份")
        if candidates:
            return candidates[0]
    return None


def _remember_map(s, family_id, skill_id, person_id, user_id, now):
    if not skill_id:
        return
    if s.query(PersonIdMap).filter_by(
            family_id=family_id, skill_id=skill_id).first():
        return
    s.add(PersonIdMap(id=new_id(), family_id=family_id, skill_id=skill_id,
                      person_id=person_id, create_by=user_id, create_date=now))


def _apply_tree_upsert(s, family_id, payload, user_id, now):
    persons = payload.get("persons") or []
    updated, to_new, mapped = [], [], []
    for sp in persons:
        name = (sp.get("fullName") or "").strip()
        if not name or name.endswith("（待核实）"):
            continue
        p = _resolve_person(s, family_id, skill_id=sp.get("id"), name=name,
                            site_id=sp.get("site_person_id"))
        if p and sp.get("site_person_id") and name != p.name and name not in (p.aliases or []):
            raise SyncError("网站人物 ID 与姓名不一致，请先核对人物，不能自动改名")
        if p:
            from person_dates import sync_legacy_year
            try:
                if sp.get("birthYear") is not None:
                    sync_legacy_year(p, "birth", sp["birthYear"])
                if sp.get("deathYear") is not None:
                    sync_legacy_year(p, "death", sp["deathYear"])
            except ValueError as exc:
                raise SyncError(str(exc)) from None
            if sp.get("alive") is not None:
                if not isinstance(sp["alive"], bool):
                    raise SyncError("alive 必须为 true 或 false")
                if sp["alive"] and p.death_date_label:
                    raise SyncError("健在与已有去世日期冲突，请在人物编辑页核实修改")
                p.alive = sp["alive"]
                p.life_status = "alive" if sp["alive"] else "deceased"
            if sp.get("deathYear") is not None and p.life_status == "unknown" and p.death_date_label:
                p.life_status = "deceased"
                p.alive = False
            if any(sp.get(field) is not None for field in ("birthYear", "deathYear", "alive")):
                from person_dates import parse_form
                try:
                    parse_form({"alive": "1" if p.alive else ""}, p)
                except ValueError as exc:
                    raise SyncError(str(exc)) from None
            if sp.get("status"):
                p.status = sp["status"]
            if sp.get("relation") and not p.relation:
                p.relation = sp["relation"]
            notes = list(p.notes or [])
            for n in sp.get("notes") or []:
                if n and n not in notes:
                    notes.append(n)
            p.notes = notes
            aliases = list(p.aliases or [])
            for a in sp.get("aliases") or []:
                if a and a not in aliases and a != p.name:
                    aliases.append(a)
            p.aliases = aliases
            p.update_by, p.update_date = user_id, now
            _remember_map(s, family_id, sp.get("id"), p.id, user_id, now)
            updated.append(p.name)
        else:
            # 对不上树 → 记 🆕，不硬挂
            exists = s.query(NewPerson).filter_by(
                family_id=family_id, name=name, del_flag=0).first()
            if not exists:
                ctx = "；".join(sp.get("notes") or [])
                if sp.get("relation"):
                    ctx = f"关系：{sp['relation']}；" + ctx
                s.add(NewPerson(id=new_id(), family_id=family_id, name=name,
                                context=ctx[:500] or None, join_tree="pending",
                                create_by=user_id, create_date=now))
            to_new.append(name)
    summary = (f"树更新：{len(updated)} 人信息已更新"
               + (f"（{ '、'.join(updated[:5])}{'…' if len(updated) > 5 else ''}）" if updated else "")
               + (f"；{len(to_new)} 位人物仍待定（{ '、'.join(to_new[:5])}），请在家人页添加真实人物，再用新包建立映射；尚不可导入关联故事" if to_new else ""))
    return None, summary


def _parse_tl_date(ds):
    """'1978' → 年精度；'1978-05' → 月精度；'1978-05-01' → 日精度。"""
    ds = (ds or "").strip()
    m = re.fullmatch(r"(\d{4})", ds)
    if m:
        return datetime.date(int(m.group(1)), 1, 1), "year"
    m = re.fullmatch(r"(\d{4})-(\d{1,2})", ds)
    if m:
        return datetime.date(int(m.group(1)), int(m.group(2)), 1), "month"
    try:
        return datetime.date.fromisoformat(ds), "day"
    except ValueError:
        return None, "year"


def _apply_interview_upsert(s, family_id, payload, user_id, now):
    topic = (payload.get("topic") or "未命名访谈").strip()
    subject = _resolve_person(s, family_id,
                              skill_id=payload.get("subject_person_id"))
    narrator = _resolve_person(s, family_id,
                               skill_id=payload.get("narrator_person_id"),
                               name=payload.get("narrator_name"))
    for key, person in (("subject_person_id", subject), ("narrator_person_id", narrator)):
        if payload.get(key) and not person:
            raise SyncError(f"{key} 未建立人物映射，请先在家人页核对人物，再提交新的 tree_upsert 包")
    remarks = None
    if payload.get("narrator_name") and not narrator:
        remarks = f"讲述者：{payload['narrator_name']}（待对应到树上人物）"

    def _d(ds):
        try:
            return datetime.date.fromisoformat(ds) if ds else None
        except ValueError:
            return None

    iv = Interview(
        id=new_id(), family_id=family_id, author_id=user_id,
        person_id=subject.id if subject else None, topic=topic, status="done",
        publish_status="published", published_at=__import__("reporting").local_now(),
        narrator_person_id=narrator.id if narrator else None,
        period_start=_d(payload.get("period_start")),
        period_end=_d(payload.get("period_end")),
        period_precision=payload.get("period_precision") or "day",
        remarks=remarks, create_by=user_id, create_date=now)
    s.add(iv)
    s.flush()

    draft_text = sanitize_html(payload.get("draft") or "", family_id)
    s.add(Draft(id=new_id(), interview_id=iv.id, version=1, is_current=True,
                content=draft_text, create_by=user_id, create_date=now))

    n_q = 0
    for q in payload.get("quotes") or []:
        if q and q.strip():
            s.add(Quote(id=new_id(), interview_id=iv.id, text=q.strip()[:500],
                        create_by=user_id, create_date=now))
            n_q += 1
    n_v = 0
    for v in payload.get("verification_items") or []:
        text = (v.get("text") if isinstance(v, dict) else v) or ""
        reason = v.get("reason") if isinstance(v, dict) else ""
        if text.strip():
            s.add(VerificationItem(id=new_id(), interview_id=iv.id,
                                   text=text.strip()[:500],
                                   reason=(reason or "")[:500],
                                   status="pending",
                                   create_by=user_id, create_date=now))
            n_v += 1
    n_t = 0
    for t in payload.get("timeline") or []:
        ev_date, prec = _parse_tl_date(t.get("date"))
        title = (t.get("event") or "").strip()
        if title:
            s.add(TimelineEvent(
                id=new_id(), family_id=family_id,
                person_id=subject.id if subject else None,
                event_date=ev_date, date_precision=prec, title=title[:128],
                source_interview_id=iv.id, create_by=user_id, create_date=now))
            n_t += 1
    # 人物关联：讲述对象 subject + 关联人物 related
    linked = []
    if subject:
        s.add(InterviewPerson(id=new_id(), interview_id=iv.id,
                              person_id=subject.id, role="subject",
                              create_by=user_id, create_date=now))
        linked.append(subject.name)
    for rp in payload.get("related_persons") or []:
        rp_id = rp.get("person_id") if isinstance(rp, dict) else rp
        role = rp.get("role") if isinstance(rp, dict) else "related"
        p = _resolve_person(s, family_id, skill_id=rp_id)
        if not p:
            raise SyncError("关联人物未建立映射，请核对后重新导入，不能静默丢失关联")
        if p and (not subject or p.id != subject.id):
            exists = s.query(InterviewPerson).filter_by(
                interview_id=iv.id, person_id=p.id, del_flag=0).first()
            if not exists:
                s.add(InterviewPerson(id=new_id(), interview_id=iv.id,
                                      person_id=p.id, role=role or "related",
                                      create_by=user_id, create_date=now))
                linked.append(p.name)
    # 人物实体链接（mention → 人物），供故事页"人物对应"展示
    if subject:
        from models import PersonLink
        s.add(PersonLink(id=new_id(), interview_id=iv.id, person_id=subject.id,
                         mention=subject.name, create_by=user_id,
                         create_date=now))
    summary = (f"初稿入库：《{topic}》"
               f"（讲述对象：{subject.name if subject else '未对应'}；"
               f"讲述者：{narrator.name if narrator else payload.get('narrator_name') or '未对应'}；"
               f"金句 {n_q} 条；待核实 {n_v} 条；时间轴 {n_t} 条；"
               f"关联人物 {len(linked)} 位）")
    return iv.id, summary


def _interview_by_client(s, family_id, client_id):
    log = s.query(SyncLog).filter_by(family_id=family_id, client_id=client_id, status="ok").first()
    if log and log.target_id:
        return log.target_id
    return None


def _editable_interview(s, family_id, interview_id, user_id):
    from access import story_editable
    iv = s.query(Interview).filter_by(
        id=interview_id, family_id=family_id, del_flag=0).with_for_update().first()
    if not iv or not story_editable(s, iv, user_id):
        raise SyncError("找不到可整理的故事，请使用有权限的账号在网页核对")
    return iv


def _set_verification(item, status, correction, user_id, now):
    if status not in ("pending", "verified", "resolved", "corrected"):
        raise SyncError("核实状态仅支持 pending/verified/resolved/corrected")
    if correction is not None and not isinstance(correction, str):
        raise SyncError("correction 必须为文字")
    if status == "corrected" and not (correction or '').strip():
        raise SyncError("更正核实项时必须填写 correction")
    item.status = "pending" if status == "pending" else "resolved"
    if correction:
        item.correction = correction.strip()[:500]
    item.update_by, item.update_date = user_id, now


def _verification_item(s, interview_id, payload):
    query = s.query(VerificationItem).filter_by(interview_id=interview_id, del_flag=0)
    if payload.get("item_id"):
        item = query.filter_by(id=payload["item_id"]).first()
        if item:
            return item
    else:
        matches = query.filter_by(text=(payload.get("item_text") or '').strip()).all()
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise SyncError("待核实原文重复，请用 item_id 明确选择，不得猜测目标")
    raise SyncError("找不到目标故事下的待核实项，请核对 item_id 或未改写的原文")


def _apply_verification_update(s, family_id, payload, user_id, now):
    iv_id = payload.get("interview_id") or _interview_by_client(
        s, family_id, payload.get("interview_client_id"))
    _editable_interview(s, family_id, iv_id, user_id)
    item = _verification_item(s, iv_id, payload)
    _set_verification(item, payload.get("status") or "resolved",
                      payload.get("correction"), user_id, now)
    return iv_id, f"核实更新：《{item.text[:20]}…》→ {item.status}"


def _apply_new_person(s, family_id, payload, user_id, now):
    name = (payload.get("name") or "").strip()
    if not name:
        raise SyncError("new_person 缺少姓名")
    exists = s.query(NewPerson).filter_by(
        family_id=family_id, name=name, del_flag=0).first()
    if exists:
        return None, f"🆕 {name} 已在待定列表，跳过"
    s.add(NewPerson(id=new_id(), family_id=family_id, name=name,
                    context=(payload.get("context") or "")[:500],
                    join_tree="pending", create_by=user_id, create_date=now))
    return None, f"🆕 新人物 {name} 记入待定"


def _apply_person_status(s, family_id, payload, user_id, now):
    p = _resolve_person(s, family_id, skill_id=payload.get("person_id"),
                        name=payload.get("name"), site_id=payload.get("site_person_id"))
    if not p:
        raise SyncError(f"找不到人物：{payload.get('name') or payload.get('person_id')}")
    p.status = payload.get("status") or p.status
    p.update_by, p.update_date = user_id, now
    _remember_map(s, family_id, payload.get("person_id"), p.id, user_id, now)
    return p.id, f"{p.name} 状态 → {p.status}"


def _apply_revision_sync(s, family_id, payload, user_id, now):
    """修订清单应用：verify 确认/修正/转下周；draft 全文修订（新版本）；person 正名。"""
    from models import PersonLink
    n_ok, notes = 0, []
    revisions = payload.get("revisions")
    if not isinstance(revisions, list) or not revisions:
        raise SyncError("revisions 必须为至少包含一项的数组")
    for rv in revisions:
        kind, action = rv.get("kind"), rv.get("action")
        if kind == "verify":
            iv_id = rv.get("interview_id") or _interview_by_client(
                s, family_id, rv.get("interview_client_id"))
            if not iv_id:
                raise SyncError("找不到待修订故事，请核对原始入库 clientId；本包全部未生效")
            _editable_interview(s, family_id, iv_id, user_id)
            item = _verification_item(s, iv_id, rv)
            if action == "confirm":
                _set_verification(item, "verified", None, user_id, now)
            elif action == "correct":
                _set_verification(item, "corrected", rv.get("correction"), user_id, now)
            elif action == "skip":
                _set_verification(item, "pending", None, user_id, now)
                item.remarks = ((item.remarks or "") + "；转下周追问").strip("；")
            else:
                raise SyncError("未知核实动作，请使用 confirm/correct/skip；本包全部未生效")
            item.update_by, item.update_date = user_id, now
            n_ok += 1
        elif kind == "draft":
            iv_id = rv.get("interview_id") or _interview_by_client(
                s, family_id, rv.get("interview_client_id"))
            if not iv_id:
                raise SyncError("找不到待修订故事，请核对原始入库 clientId；本包全部未生效")
            iv = _editable_interview(s, family_id, iv_id, user_id)
            new_text = sanitize_html(rv.get("draft") or "", family_id)
            if not new_text:
                raise SyncError("修订正文不能为空；本包全部未生效")
            from story_revisions import append_revision
            try:
                append_revision(s, iv, user_id, new_text, rv.get("base_version"),
                                rv.get("revision_reason"))
            except ValueError as exc:
                raise SyncError(str(exc)) from None
            n_ok += 1
        elif kind == "person":
            p = _resolve_person(s, family_id, skill_id=rv.get("person_id"),
                                site_id=rv.get("site_person_id"), name=rv.get("name"))
            full = (rv.get("full_name") or "").strip()
            if not p or not full:
                raise SyncError("正名缺少明确人物或新姓名；本包全部未生效")
            if p.name != full:
                old = p.name
                p.notes = list(p.notes or []) + [f"曾用名：{old}"]
                p.name = full
                p.update_by, p.update_date = user_id, now
                notes.append(f"正名：{old} → {full}")
                n_ok += 1
            else:
                notes.append("人物姓名已一致，无需正名")
        else:
            raise SyncError("未知修订类型，请使用 verify/draft/person；本包全部未生效")
    summary = f"修订应用：{n_ok} 条生效" + (f"；{ '；'.join(notes[:5])}" if notes else "")
    return None, summary


def _apply_plan_progress(s, family_id, payload, user_id, now):
    """skill 回写计划进度：{plan_id?, items:[{person_id(skill侧id)/person_name, status}]}。
    plan_id 缺省用当前计划；人物走映射表→姓名匹配；只更新 status。"""
    import json as _json
    plan_id = payload.get("plan_id")
    if plan_id:
        plan = s.query(WritingPlan).filter_by(
            id=plan_id, family_id=family_id, del_flag=0).first()
    else:
        plan = s.query(WritingPlan).filter_by(
            family_id=family_id, status="active", del_flag=0).order_by(
            WritingPlan.update_date.desc()).first()
    if not plan:
        raise SyncError("没有可更新的写作计划（plan_id 不对或无当前计划）")
    try:
        items = _json.loads(plan.items or "[]")
    except ValueError:
        items = []
    wanted = {}
    progress_items = payload.get("items")
    if not isinstance(progress_items, list) or not progress_items:
        raise SyncError("计划进度 items 必须为至少包含一项的数组")
    for it in progress_items:
        st = it.get("status")
        if st not in ("pending", "doing", "done"):
            raise SyncError("计划状态仅支持 pending/doing/done；本包全部未生效")
        p = _resolve_person(s, family_id,
                            skill_id=it.get("person_id"),
                            name=it.get("person_name"), site_id=it.get("site_person_id"))
        if not p or not any(row.get("person_id") == p.id for row in items):
            raise SyncError("人物未对应到该计划，请核对映射或使用计划返回的网站 ID 填入 site_person_id")
        wanted[p.id] = st
    n = 0
    for it in items:
        if it.get("person_id") in wanted:
            it["status"] = wanted[it["person_id"]]
            n += 1
    plan.items = _json.dumps(items, ensure_ascii=False)
    plan.update_by = user_id
    plan.update_date = now
    return plan.id, f"写作计划《{plan.title}》进度更新 {n} 人"


_HANDLERS = {
    "tree_upsert": _apply_tree_upsert,
    "interview_upsert": _apply_interview_upsert,
    "verification_update": _apply_verification_update,
    "new_person": _apply_new_person,
    "person_status": _apply_person_status,
    "revision_sync": _apply_revision_sync,
    "plan_progress": _apply_plan_progress,
}


def apply_sync(s, family_id, packet, user_id):
    """应用一个 sync-json 数据包。返回 (ok, summary)。幂等，失败抛 SyncError。"""
    if not isinstance(packet, dict) or not isinstance(packet.get("payload", {}), dict):
        raise SyncError("数据包及 payload 必须是 JSON 对象")
    ptype = (packet or {}).get("type")
    client_id = (packet or {}).get("clientId")
    payload = (packet or {}).get("payload") or {}
    if ptype not in SUPPORTED:
        raise SyncError(f"未知的数据包类型：{ptype}（支持 {', '.join(SUPPORTED)}）")
    if not isinstance(client_id, str) or not client_id or len(client_id) > 64:
        raise SyncError("clientId 必须是 1-64 字符的字符串，请 skill 侧生成 uuid")
    dup = s.query(SyncLog).filter_by(client_id=client_id).first()
    if dup:
        return False, f"重复数据包，已跳过（{dup.create_date:%Y-%m-%d %H:%M} 已入库）"
    now = datetime.datetime.now()
    try:
        target_id, summary = _HANDLERS[ptype](s, family_id, payload, user_id, now)
        s.add(SyncLog(id=new_id(), family_id=family_id, op_type=ptype,
                      client_id=client_id, target_id=target_id, status="ok",
                      summary=summary[:500], create_by=user_id, create_date=now))
        s.commit()
    except (ValueError, TypeError, KeyError, AttributeError, SQLAlchemyError):
        s.rollback()
        raise SyncError("同步数据无效或写入失败，请核对字段类型与目标记录") from None
    except Exception:
        s.rollback()
        raise
    return True, summary


# 当前同步契约见 memoir-sync-design.md；人物候选不等于真实人物或映射。


def log_sync_failure(s, family_id, packet, user_id, error):
    """入库失败也记一笔（client_id 加 failed: 前缀，不占用幂等键）。"""
    now = datetime.datetime.now()
    packet = packet if isinstance(packet, dict) else {}
    client_id = packet.get("clientId") or new_id()
    s.add(SyncLog(id=new_id(), family_id=family_id,
                  op_type=str(packet.get("type") or "unknown")[:32],
                  client_id=f"failed:{new_id()}", target_id=None,
                  remarks=f"原包 clientId: {client_id}"[:255],
                  status="failed", summary=str(error)[:500],
                  create_by=user_id, create_date=now))
    s.commit()

