"""sync-json 入库引擎：把 skill 输出的数据包写入本站 DB。

数据包格式见 memoir-sync-design.md §五（网站侧实现补充见文末注释）。

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

SUPPORTED = ("tree_upsert", "interview_upsert", "verification_update",
             "new_person", "person_status", "revision_sync", "plan_progress")


class SyncError(Exception):
    pass


def sanitize_html(content):
    # 仅在写入正文时加载清洗器；所有正文入口仍使用同一白名单。
    from sanitize import sanitize_html as clean
    return clean(content)


def _resolve_person(s, family_id, skill_id=None, name=None):
    """skill 人物 → 本站 Person：先查映射表，再姓名精确匹配，再别名匹配。"""
    if skill_id:
        m = s.query(PersonIdMap).filter_by(
            family_id=family_id, skill_id=skill_id).first()
        if m:
            p = s.query(Person).filter_by(id=m.person_id, family_id=family_id, del_flag=0).first()
            if p:
                return p
    if name:
        p = s.query(Person).filter_by(
            family_id=family_id, name=name, del_flag=0).first()
        if p:
            return p
        # 别名匹配
        for cand in s.query(Person).filter_by(family_id=family_id,
                                               del_flag=0).all():
            if name in (cand.aliases or []):
                return cand
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
        p = _resolve_person(s, family_id, skill_id=sp.get("id"), name=name)
        if p:
            if sp.get("birthYear"):
                p.birth_year = sp["birthYear"]
            if sp.get("deathYear"):
                p.death_year = sp["deathYear"]
            if sp.get("alive") is not None:
                p.alive = bool(sp["alive"])
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
               + (f"；{len(to_new)} 位新人物记入待定（{ '、'.join(to_new[:5])}）" if to_new else ""))
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
        publish_status="published",
        narrator_person_id=narrator.id if narrator else None,
        period_start=_d(payload.get("period_start")),
        period_end=_d(payload.get("period_end")),
        period_precision=payload.get("period_precision") or "day",
        remarks=remarks, create_by=user_id, create_date=now)
    s.add(iv)
    s.flush()

    draft_text = sanitize_html(payload.get("draft") or "")
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


def _apply_verification_update(s, family_id, payload, user_id, now):
    iv_id = payload.get("interview_id") or _interview_by_client(
        s, family_id, payload.get("interview_client_id"))
    if not iv_id or not s.query(Interview).filter_by(
            id=iv_id, family_id=family_id, del_flag=0).first():
        raise SyncError("找不到本家庭对应访谈")
    item_text = (payload.get("item_text") or "").strip()
    q = s.query(VerificationItem).filter_by(interview_id=iv_id, del_flag=0)
    item = None
    if payload.get("item_id"):
        item = q.filter_by(id=payload["item_id"]).first()
    if not item and item_text:
        item = q.filter(VerificationItem.text == item_text).first()
    if not item:
        raise SyncError(f"访谈下找不到待核实项：{item_text[:30]}")
    status = payload.get("status") or "resolved"
    item.status = "resolved" if status in ("verified", "resolved") else status
    if payload.get("correction"):
        item.correction = payload["correction"][:500]
    item.update_by, item.update_date = user_id, now
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
                        name=payload.get("name"))
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
    for rv in payload.get("revisions") or []:
        kind, action = rv.get("kind"), rv.get("action")
        if kind == "verify":
            iv_id = rv.get("interview_id") or _interview_by_client(
                s, family_id, rv.get("interview_client_id"))
            if iv_id and not s.query(Interview).filter_by(
                    id=iv_id, family_id=family_id, del_flag=0).first():
                raise SyncError("修订目标不属于本家庭")
            if not iv_id:
                notes.append(f"跳过：找不到访谈（{rv.get('item_text', '')[:15]}）")
                continue
            item = s.query(VerificationItem).filter_by(
                interview_id=iv_id, del_flag=0)
            if rv.get("item_id"):
                item = item.filter_by(id=rv["item_id"]).first()
            else:
                item = item.filter(
                    VerificationItem.text == (rv.get("item_text") or "")).first()
            if not item:
                notes.append(f"跳过：找不到核实项（{rv.get('item_text', '')[:15]}）")
                continue
            if action == "confirm":
                item.status = "resolved"
            elif action == "correct":
                item.status = "resolved"
                item.correction = (rv.get("correction") or "")[:500]
            elif action == "skip":
                item.status = "pending"
                item.remarks = ((item.remarks or "") + "；转下周追问").strip("；")
            else:
                notes.append(f"跳过：未知动作 {action}")
                continue
            item.update_by, item.update_date = user_id, now
            n_ok += 1
        elif kind == "draft":
            iv_id = rv.get("interview_id") or _interview_by_client(
                s, family_id, rv.get("interview_client_id"))
            if iv_id and not s.query(Interview).filter_by(
                    id=iv_id, family_id=family_id, del_flag=0).first():
                raise SyncError("修订目标不属于本家庭")
            if not iv_id:
                notes.append("跳过：修订找不到访谈")
                continue
            new_text = sanitize_html(rv.get("draft") or "")
            if not new_text:
                notes.append("跳过：修订正文为空")
                continue
            cur = s.query(Draft).filter_by(interview_id=iv_id, is_current=True,
                                           del_flag=0).first()
            if cur:
                cur.is_current = False
                ver = (cur.version or 1) + 1
            else:
                ver = 1
            s.add(Draft(id=new_id(), interview_id=iv_id, version=ver,
                        is_current=True, content=new_text,
                        create_by=user_id, create_date=now))
            n_ok += 1
        elif kind == "person":
            p = _resolve_person(s, family_id, name=rv.get("name"))
            full = (rv.get("full_name") or "").strip()
            if p and full and p.name != full:
                old = p.name
                p.notes = list(p.notes or []) + [f"曾用名：{old}"]
                p.name = full
                p.update_by, p.update_date = user_id, now
                notes.append(f"正名：{old} → {full}")
                n_ok += 1
            else:
                notes.append(f"跳过：人物 {rv.get('name')} 未找到或无需正名")
        else:
            notes.append(f"跳过：未知修订类型 {kind}")
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
    for it in payload.get("items", []):
        st = it.get("status")
        if st not in ("pending", "doing", "done"):
            continue
        p = _resolve_person(s, family_id,
                            skill_id=it.get("person_id"),
                            name=it.get("person_name"))
        if p:
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
    if not client_id:
        raise SyncError("缺少 clientId（幂等去重用），请 skill 侧生成 uuid")
    dup = s.query(SyncLog).filter_by(client_id=client_id).first()
    if dup:
        return False, f"重复数据包，已跳过（{dup.create_date:%Y-%m-%d %H:%M} 已入库）"
    now = datetime.datetime.now()
    try:
        target_id, summary = _HANDLERS[ptype](s, family_id, payload, user_id, now)
    except Exception:
        s.rollback()
        raise
    s.add(SyncLog(id=new_id(), family_id=family_id, op_type=ptype,
                  client_id=client_id, target_id=target_id, status="ok",
                  summary=summary[:500], create_by=user_id, create_date=now))
    s.commit()
    return True, summary


# 网站侧入库实现补充（对应 sync-design.md §五）：
# - tree_upsert：只更新已有人物信息字段（姓名精确/别名匹配），不自动改挂靠；
#   对不上的人记入 new_persons（join_tree=pending），并建立 skill_id→person_id 映射。
# - interview_upsert：人物解析走映射表→姓名匹配；讲述者对不上时 narrator_person_id
#   留空、narrator_name 记入 interviews.remarks；幂等键 clientId。
# - revision_sync（网站侧定义）：revisions 数组，kind=verify/draft/person：
#   verify: {interview_client_id|interview_id, item_text|item_id, action=confirm|correct|skip, correction?}
#   draft: {interview_client_id|interview_id, draft}（全文修订，生成新版本）
#   person: {name, full_name}（正名，旧名记入备注）
# - plan_progress（skill 回写）：{plan_id?, items:[{person_id(skill侧)/person_name, status=pending|doing|done}]}（只更新计划条目状态）


def log_sync_failure(s, family_id, packet, user_id, error):
    """入库失败也记一笔（client_id 加 failed: 前缀，不占用幂等键）。"""
    now = datetime.datetime.now()
    packet = packet if isinstance(packet, dict) else {}
    client_id = packet.get("clientId") or new_id()
    s.add(SyncLog(id=new_id(), family_id=family_id,
                  op_type=packet.get("type") or "unknown",
                  client_id=f"failed:{client_id}", target_id=None,
                  status="failed", summary=str(error)[:500],
                  create_by=user_id, create_date=now))
    s.commit()

