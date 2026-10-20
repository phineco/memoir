"""AI 能力：DeepSeek API 直调 + 预置提示词。

- chat(family_id, user_id, message)：家庭知识库问答。AI 知道项目的架构/目的/功能，
  以家庭已有内容为知识库，按用户记忆提供针对性服务，并引导用户完善缺失内容、做规划。
- summarize_weekly(family_id, week)：周报 AI 导读（按周缓存，生成一次重复用）。
- 用户记忆：ai_memories（每用户一条 profile），每次对话后自动提炼更新。

未配置 DEEPSEEK_API_KEY 时 AI_ENABLED=False，所有入口优雅降级（按钮隐藏/提示配置）。
"""
import datetime
import json
import re

import requests

from config import Config
from models import (AiCache, AiMemory, AiMessage, Draft, Interview, InterviewViewer,
                    NewPerson, Person, Quote, VerificationItem, get_session, new_id)


class AIError(Exception):
    pass


def ai_enabled():
    return bool(Config.AI_ENABLED)


def _s():
    return get_session()


def _safe_user_id(uid):
    """清洗为 DeepSeek user_id 允许的格式（不含隐私信息）。"""
    cleaned = re.sub(r"[^a-zA-Z0-9\-_]", "-", str(uid or ""))[:512]
    return cleaned or None


# ---------------- 底层调用 ----------------

def _chat_complete(messages, temperature=0.7, max_tokens=1500,
                   json_mode=False, timeout=60, user_id=None):
    """调 DeepSeek chat completions（OpenAI 兼容接口）。

    user_id：按官方 rate_limit 文档做用户隔离（内容安全/KVCache/调度三层），
    须满足 [a-zA-Z0-9\\-_]+ 且不含隐私信息；本站用不透明的内部 user id。
    """
    if not ai_enabled():
        raise AIError("AI 未启用：请配置 DEEPSEEK_API_KEY")
    body = {"model": Config.DEEPSEEK_MODEL, "messages": messages,
            "temperature": temperature, "max_tokens": max_tokens}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    safe_uid = _safe_user_id(user_id)
    if safe_uid:
        body["user_id"] = safe_uid
    try:
        r = requests.post(
            Config.DEEPSEEK_BASE_URL.rstrip("/") + "/chat/completions",
            headers={"Authorization": "Bearer " + Config.DEEPSEEK_API_KEY,
                     "Content-Type": "application/json"},
            json=body, timeout=timeout)
    except requests.RequestException as e:
        raise AIError("AI 接口连接失败：%s" % e)
    if r.status_code == 429:
        raise AIError("AI 繁忙（触发并发限速），请稍后再试")
    if r.status_code != 200:
        raise AIError("AI 接口返回 %s：%s" % (r.status_code, r.text[:200]))
    try:
        return r.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError):
        raise AIError("AI 接口返回格式异常")


# ---------------- 家庭知识库 ----------------

_STATUS_LABEL = {"pending": "待采访", "doing": "整理中",
                 "drafted": "初稿完成", "verified": "已核实"}


def _story_visible_to(iv, viewer_id, visible_ids):
    """AI 知识库用：故事是否对 viewer_id 可见。viewer_id 为空时只取公开。"""
    if (iv.publish_status or "published") != "published":
        return False
    vis = iv.visibility or "public"
    if vis == "public":
        return True
    if not viewer_id:
        return False
    return iv.author_id == viewer_id or iv.id in visible_ids


def family_knowledge(family_id, viewer_id=None, limit=6000):
    """把家庭已有内容组装成 AI 的知识库文本（有界）。只含 viewer 可见的故事。"""
    s = _s()
    parts = []
    persons = s.query(Person).filter_by(
        family_id=family_id, del_flag=0).order_by(Person.sort).all()
    if persons:
        lines = []
        for p in persons:
            life = "%s–%s" % (p.birth_year or "?",
                              p.death_year or ("今" if p.alive else "?"))
            st = _STATUS_LABEL.get(p.status or "", "")
            lines.append("- %s（%s，%s%s）" % (
                p.name, p.relation or "关系未知", life,
                "，" + st if st else ""))
        parts.append("人物（家族树）：\n" + "\n".join(lines))
    visible_ids = set()
    if viewer_id:
        visible_ids = {v.interview_id for v in s.query(InterviewViewer).filter_by(
            user_id=viewer_id, del_flag=0).all()}
    interviews = [iv for iv in s.query(Interview).filter_by(
        family_id=family_id, del_flag=0).all()
        if _story_visible_to(iv, viewer_id, visible_ids)]
    if interviews:
        lines = []
        for iv in interviews:
            d = s.query(Draft).filter_by(
                interview_id=iv.id, is_current=True, del_flag=0).first()
            excerpt = ""
            if d and d.content:
                excerpt = re.sub(r"<[^>]+>", "",
                                 d.content.replace("\n", " "))[:200]
            lines.append("- 《%s》：%s" % (iv.topic, excerpt))
        parts.append("故事：\n" + "\n".join(lines))
    quotes = s.query(Quote).join(
        Interview, Quote.interview_id == Interview.id).filter(
        Interview.family_id == family_id,
        Quote.del_flag == 0).limit(8).all()
    if quotes:
        parts.append("金句：\n" + "\n".join("- %s" % q.text for q in quotes))
    verifs = s.query(VerificationItem).join(
        Interview, VerificationItem.interview_id == Interview.id).filter(
        Interview.family_id == family_id, VerificationItem.status == "pending",
        VerificationItem.del_flag == 0).limit(10).all()
    if verifs:
        parts.append("待核实（还没解决）：\n" +
                     "\n".join("- %s" % v.text for v in verifs))
    nps = s.query(NewPerson).filter_by(
        family_id=family_id, join_tree="pending", del_flag=0).limit(8).all()
    if nps:
        parts.append("待定是否入树的新人物：\n" +
                     "\n".join("- %s（%s）" % (n.name, n.context or "")
                               for n in nps))
    text = "\n\n".join(parts) or "（这个家庭还没有录入任何内容）"
    return text[:limit]


def _user_memory(family_id, user_id):
    s = _s()
    m = s.query(AiMemory).filter_by(
        family_id=family_id, user_id=user_id, memory_key="profile",
        del_flag=0).first()
    return m.content if m and m.content else "（暂无，第一次交流）"


# ---------------- 预置提示词 ----------------

def _system_prompt(family_name, knowledge, memory):
    return (
        "你是\"家音\"——家庭口述回忆录的 AI 助手。\n\n"
        "【项目】\n"
        "家音帮家庭把老人的口述留成回忆录：老人口述（电话/录音）→ AI 整理成初稿 → 入库 → "
        "每周周报全家传阅纠正 → 人工确认后发布分享页 → 印成书。\n"
        "网站功能：家族树（人物/称谓/认领）、故事（阅读/朗读/评论/点赞）、"
        "写文章（富文本/语音输入/草稿箱）、照片墙、人物小传、时间轴、周报、"
        "分享页（人工确认发布）、sync-json 同步入库、AI 问答（就是你）。\n"
        "最高红线：绝不虚构。知识库里没有的，直说\"回忆录里没记这事\"。\n\n"
        "【%s 家庭知识库】\n%s\n\n"
        "【关于这位用户】\n%s\n\n"
        "【你要做的事】\n"
        "1. 回答关于家庭、回忆、故事的问题：答案必须来自知识库，并注明来源"
        "（如\"出自《供销社的那些年》\"/\"王建军的小传里写到\"）；没有依据就直说不知道。\n"
        "2. 主动发现缺失并引导补充：谁还没小传、谁的待核实没解决、哪位长辈还没采访"
        "——一次只提 1-2 个最值得补的，问用户要不要做。\n"
        "3. 帮用户做规划：如下周采访谁、待办清单。\n"
        "4. 也可以解答网站怎么用。\n\n"
        "【说话方式】\n"
        "简体中文，简短直接，像家人聊天。一次聚焦一件事，不要长篇大论。"
        % (family_name, knowledge, memory)
    )


def _memory_extract_prompt(old_memory, recent):
    return (
        "根据以下对话，提炼关于这位用户的长期有效信息（他是谁、偏好、正在做的事、家人情况），"
        "用于下次提供针对性服务。只记事实，不推测。没有新信息就输出空字符串。\n\n"
        "已有记忆：%s\n\n最近对话：\n%s\n\n"
        "输出 JSON：{\"memory\": \"提炼后的一段话（与已有记忆合并去重），无新信息则为空字符串\"}"
        % (old_memory, recent)
    )


_WEEKLY_PROMPT = (
    "你是\"家音\"回忆录的编辑。请根据本周家庭周报数据，写一段 200-300 字的\"本周导读\"，\n"
    "再列 3 条\"本周看点\"（一句话一条）。要求：温暖、口语化，像家人群里的分享；\n"
    "只基于给的数据，不虚构；有待核实事项可以提一句\"等全家一起核实\"。\n\n"
    "数据：\n{weekly_json}\n\n"
    "只输出 JSON：{{\"digest\": \"...\", \"highlights\": [\"...\", \"...\", \"...\"]}}"
)


# ---------------- 对外接口 ----------------

def _chat_complete_stream(messages, temperature=0.7, max_tokens=1500,
                          user_id=None):
    """流式调用 DeepSeek：逐块产出回复文本（str）。"""
    if not ai_enabled():
        raise AIError("AI 未启用：请配置 DEEPSEEK_API_KEY")
    body = {"model": Config.DEEPSEEK_MODEL, "messages": messages,
            "temperature": temperature, "max_tokens": max_tokens,
            "stream": True}
    safe_uid = _safe_user_id(user_id)
    if safe_uid:
        body["user_id"] = safe_uid
    try:
        r = requests.post(
            Config.DEEPSEEK_BASE_URL.rstrip("/") + "/chat/completions",
            headers={"Authorization": "Bearer " + Config.DEEPSEEK_API_KEY,
                     "Content-Type": "application/json"},
            json=body, timeout=120, stream=True)
    except requests.RequestException as e:
        raise AIError("AI 接口连接失败：%s" % e)
    if r.status_code == 429:
        raise AIError("AI 繁忙（触发并发限速），请稍后再试")
    if r.status_code != 200:
        raise AIError("AI 接口返回 %s：%s" % (r.status_code, r.text[:200]))
    r.encoding = "utf-8"
    for line in r.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            break
        try:
            chunk = json.loads(payload)
            delta = chunk["choices"][0].get("delta") or {}
            piece = delta.get("content") or ""
        except (KeyError, IndexError, ValueError):
            continue
        if piece:
            yield piece


def chat_stream(family_id, user_id, message, family_name=""):
    """流式一轮问答：逐块产出回复；结束后存档并更新用户记忆。"""
    message = (message or "").strip()
    if not message:
        raise AIError("消息不能为空")
    s = _s()
    knowledge = family_knowledge(family_id, viewer_id=user_id)
    memory = _user_memory(family_id, user_id)
    history = s.query(AiMessage).filter_by(
        family_id=family_id, user_id=user_id, del_flag=0).order_by(
        AiMessage.create_date.desc()).limit(10).all()
    history = list(reversed(history))
    messages = [{"role": "system",
                 "content": _system_prompt(family_name or "本家庭",
                                           knowledge, memory)}]
    for h in history:
        messages.append({"role": h.role, "content": h.content})
    messages.append({"role": "user", "content": message})

    parts = []
    for piece in _chat_complete_stream(messages, user_id=user_id):
        parts.append(piece)
        yield piece
    reply = "".join(parts)
    now = datetime.datetime.now()
    s.add(AiMessage(id=new_id(), family_id=family_id, user_id=user_id,
                    role="user", content=message[:4000],
                    create_by=user_id, create_date=now))
    s.add(AiMessage(id=new_id(), family_id=family_id, user_id=user_id,
                    role="assistant", content=reply[:4000],
                    create_by=user_id, create_date=now))
    s.commit()
    _update_memory(family_id, user_id)


def chat(family_id, user_id, message, family_name=""):
    """一轮问答：组装提示词 → 调用 → 存档 → 更新用户记忆。返回 AI 回复。"""
    message = (message or "").strip()
    if not message:
        raise AIError("消息不能为空")
    s = _s()
    knowledge = family_knowledge(family_id, viewer_id=user_id)
    memory = _user_memory(family_id, user_id)
    history = s.query(AiMessage).filter_by(
        family_id=family_id, user_id=user_id, del_flag=0).order_by(
        AiMessage.create_date.desc()).limit(10).all()
    history = list(reversed(history))
    messages = [{"role": "system",
                 "content": _system_prompt(family_name or "本家庭",
                                           knowledge, memory)}]
    for h in history:
        messages.append({"role": h.role, "content": h.content})
    messages.append({"role": "user", "content": message})

    reply = _chat_complete(messages, user_id=user_id)
    now = datetime.datetime.now()
    s.add(AiMessage(id=new_id(), family_id=family_id, user_id=user_id,
                    role="user", content=message[:4000],
                    create_by=user_id, create_date=now))
    s.add(AiMessage(id=new_id(), family_id=family_id, user_id=user_id,
                    role="assistant", content=reply[:4000],
                    create_by=user_id, create_date=now))
    s.commit()
    _update_memory(family_id, user_id)
    return reply


def _update_memory(family_id, user_id):
    """从最近对话提炼用户记忆（失败不影响主流程）。"""
    try:
        s = _s()
        old = _user_memory(family_id, user_id)
        recent = s.query(AiMessage).filter_by(
            family_id=family_id, user_id=user_id, del_flag=0).order_by(
            AiMessage.create_date.desc()).limit(6).all()
        if not recent:
            return
        convo = "\n".join(
            "%s：%s" % ("用户" if m.role == "user" else "AI", m.content[:500])
            for m in reversed(recent))
        out = _chat_complete(
            [{"role": "user",
              "content": _memory_extract_prompt(old, convo)}],
            temperature=0.3, max_tokens=300, json_mode=True, timeout=30,
            user_id=user_id)
        new_mem = (json.loads(out).get("memory") or "").strip()
        if not new_mem:
            return
        now = datetime.datetime.now()
        m = s.query(AiMemory).filter_by(
            family_id=family_id, user_id=user_id, memory_key="profile",
            del_flag=0).first()
        if m:
            m.content = new_mem[:2000]
            m.update_date = now
        else:
            s.add(AiMemory(id=new_id(), family_id=family_id, user_id=user_id,
                           memory_key="profile", content=new_mem[:2000],
                           create_by=user_id, create_date=now))
        s.commit()
    except Exception:
        pass  # 记忆更新失败不影响问答


def get_weekly_summary(family_id, week):
    """读缓存的周报导读（dict 或 None）。"""
    s = _s()
    c = s.query(AiCache).filter_by(
        cache_key="weekly:%s:%s" % (family_id, week), del_flag=0).first()
    if not c or not c.content:
        return None
    try:
        return json.loads(c.content)
    except ValueError:
        return None


def summarize_weekly(family_id, week, weekly_json, force=False, user_id=None):
    """生成周报 AI 导读并缓存。weekly_json 为周报聚合 dict。返回 dict。"""
    if not force:
        cached = get_weekly_summary(family_id, week)
        if cached:
            return cached
    slim = {"stories": [{"topic": st.get("topic"), "person": st.get("person"),
                         "narrator": st.get("narrator")}
                        for st in weekly_json.get("stories", [])],
            "quotes": weekly_json.get("quotes", [])[:8],
            "verification_items": [
                {"text": v.get("text"), "status": v.get("status")}
                for v in weekly_json.get("verification_items", [])][:10],
            "new_persons": [n.get("name")
                            for n in weekly_json.get("new_persons", [])]}
    out = _chat_complete(
        [{"role": "user",
          "content": _WEEKLY_PROMPT.format(
              weekly_json=json.dumps(slim, ensure_ascii=False))}],
        temperature=0.8, max_tokens=800, json_mode=True, user_id=user_id)
    data = json.loads(out)
    s = _s()
    now = datetime.datetime.now()
    key = "weekly:%s:%s" % (family_id, week)
    c = s.query(AiCache).filter_by(cache_key=key, del_flag=0).first()
    blob = json.dumps(data, ensure_ascii=False)
    if c:
        c.content = blob
        c.update_date = now
    else:
        s.add(AiCache(id=new_id(), family_id=family_id, cache_key=key,
                      content=blob, create_date=now))
    s.commit()
    return data


# ---------------- 写作计划建议 ----------------

_PLAN_PROMPT = (
    "你是\"家音\"回忆录的编辑。请根据家庭知识库，为【{family_name}】制定一份\"写作/采访计划\"："
    "按优先级排序，先写谁、后写谁。\n\n"
    "排序原则：\n"
    "1. 年长、健康状况不确定的长辈优先（时间不等人）\n"
    "2. 状态为\"待采访\"的人优先于\"整理中/初稿完成\"\n"
    "3. 有故事线索但没深挖的人优先\n"
    "4. 已\"核实定稿\"的人排最后或不列入\n\n"
    "人物 id 与姓名对照（person_id 必须原样使用）：\n{id_map}\n\n"
    "知识库：\n{knowledge}\n\n"
    "只输出 JSON：{{\"title\": \"如：王家·冬季采访计划\", "
    "\"items\": [{{\"person_id\": \"p01\", \"person_name\": \"王德顺\", "
    "\"reason\": \"一句话理由\"}}]}}，最多 8 人。"
)


def suggest_writing_plan(family_id, family_name="", user_id=None):
    """AI 给出写作/采访计划建议。返回 {title, items:[{person_id, person_name, reason}]}。"""
    s = _s()
    persons = s.query(Person).filter_by(
        family_id=family_id, del_flag=0).order_by(Person.sort).all()
    valid = {p.id: p.name for p in persons}
    if not valid:
        raise AIError("这个家庭还没有人物，先建家族树")
    id_map = "\n".join("%s = %s" % (pid, name)
                       for pid, name in valid.items())
    out = _chat_complete(
        [{"role": "user",
          "content": _PLAN_PROMPT.format(
              family_name=family_name or "本家庭",
              id_map=id_map,
              knowledge=family_knowledge(family_id))}],
        temperature=0.7, max_tokens=1000, json_mode=True, user_id=user_id)
    data = json.loads(out)
    items = []
    for it in data.get("items", [])[:8]:
        pid = it.get("person_id")
        if pid in valid:
            items.append({"person_id": pid,
                          "person_name": valid[pid],
                          "reason": it.get("reason", "")})
    if not items:
        raise AIError("AI 未能给出有效建议，请重试")
    return {"title": data.get("title") or "写作/采访计划", "items": items}
