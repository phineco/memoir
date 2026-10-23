"""Bounded, private text exports. No database dumps, media URLs or saved bundles."""
import datetime
import hashlib
import io
import json
import math
import zipfile
from zoneinfo import ZoneInfo

from flask import abort, render_template
from sqlalchemy import func, or_

from config import Config
from models import Draft, Interview, Person, User
from sanitize import sanitize_html

BATCH_SIZE = 100
MAX_ALL_STORIES = 1000
MAX_STORY_BYTES = 2 * 1024 * 1024
MAX_TEXT_BYTES = 8 * 1024 * 1024
SCOPE_LABELS = {'own':'我记录的文章与草稿', 'family':'全家可见的已发布文章'}


def scope_query(s, family_id, user_id, scope):
    q = s.query(Interview).filter_by(family_id=family_id, del_flag=0)
    if scope == 'own':
        return q.filter(Interview.author_id == user_id)
    if scope == 'family':
        return q.filter(or_(Interview.publish_status == 'published', Interview.publish_status.is_(None)),
                        or_(Interview.visibility == 'public', Interview.visibility.is_(None)))
    abort(400, '导出范围无效')


def selection(q, batch):
    total = q.count()
    pages = max(1, math.ceil(total / BATCH_SIZE))
    if batch < 1 or batch > pages:
        abort(400, '导出批次已变化，请重新打开导出页面')
    rows = q.order_by(Interview.create_date, Interview.id).offset((batch-1)*BATCH_SIZE).limit(BATCH_SIZE).all()
    return rows, total, pages


def _iso(value):
    return value.isoformat() if value else None


def _period(story):
    def label(value):
        if not value:
            return '未知'
        if story.period_precision == 'year':
            return str(value.year) + '年'
        if story.period_precision == 'month':
            return value.strftime('%Y年%m月')
        if story.period_precision == 'day':
            return value.isoformat()
        return '精度未标明（保存的区间边界：' + value.isoformat() + '）'
    if not story.period_start and not story.period_end:
        return '未知'
    start, end = label(story.period_start), label(story.period_end)
    return start if start == end else start + ' 至 ' + end


def current_drafts(s, ids):
    meta = s.query(Draft.interview_id, Draft.id, Draft.version, Draft.content).filter(
        Draft.interview_id.in_(ids), Draft.is_current.is_(True), Draft.del_flag == 0).all()
    result = {}
    for row in meta:
        if row.interview_id in result or row.content is None:
            abort(409, '有文章的当前正文版本需要核对，本次未生成文件，请联系家庭管理员')
        result[row.interview_id] = row
    if set(result) != set(ids):
        abort(409, '有文章缺少当前正文，本次未生成文件，请联系家庭管理员')
    return result


def revision_marks(rows, drafts):
    return {story.id:(story.author_id, story.visibility, story.publish_status,
                      drafts[story.id].id, drafts[story.id].version,
                      hashlib.sha256((drafts[story.id].content or '').encode()).hexdigest(),
                      story.topic, story.person_id, story.narrator_person_id,
                      story.period_start, story.period_end, story.period_precision,
                      story.create_date, story.published_at)
            for story in rows}


def prepare(s, family, user_id, scope, batch, mode):
    q = scope_query(s, family.id, user_id, scope)
    if mode == 'all':
        rows = q.order_by(Interview.create_date, Interview.id).limit(MAX_ALL_STORIES+1).all()
        if len(rows) > MAX_ALL_STORIES:
            abort(413, '文章较多，请返回导出页面，按每批 100 篇分别下载；本次没有生成不完整文件')
        total = len(rows)
    elif mode == 'batch':
        rows, total, _ = selection(q, batch)
    else:
        abort(400, '导出方式无效')
    if not rows:
        abort(400, '当前范围还没有可导出的文章')
    ids = [row.id for row in rows]
    # Check body lengths before loading text; exports never consume unbounded media.
    sizes = s.query(Draft.interview_id, func.length(Draft.content)).filter(
        Draft.interview_id.in_(ids), Draft.is_current.is_(True), Draft.del_flag == 0).all()
    if any((length or 0) > MAX_STORY_BYTES for _, length in sizes) or sum(length or 0 for _, length in sizes) > MAX_TEXT_BYTES:
        abort(413, '本次正文较大，请按批次下载；单篇过大时请联系管理员，本次未生成文件')
    drafts = current_drafts(s, ids)
    people = {p.id:p.name for p in s.query(Person).filter_by(family_id=family.id, del_flag=0).all()}
    authors = {u.id:u.nickname or u.username or '家人' for u in s.query(User).filter(
        User.id.in_({row.author_id for row in rows if row.author_id}), User.del_flag == 0).all()}
    records = []
    budget = 0
    for story in rows:
        draft = drafts[story.id]
        raw = draft.content.encode('utf-8')
        if len(raw) > MAX_STORY_BYTES:
            abort(413, '有单篇正文过大，请联系管理员核对，本次未生成文件')
        record = dict(id=story.id, title=story.topic or '未命名回忆',
            author=authors.get(story.author_id, '家人（未记名）'),
            subject=people.get(story.person_id, '未指定'), narrator=people.get(story.narrator_person_id, '未指定'),
            status='草稿' if story.publish_status == 'draft' else '已发布',
            visibility={'public':'全家人可见','private':'仅自己可见','specific':'指定人可见'}.get(story.visibility or 'public', '未标明'),
            created_at=_iso(story.create_date),
            published_at=_iso(story.published_at) if story.publish_status != 'draft' else None,
            publication_estimate=_iso(story.create_date) if story.publish_status != 'draft' and not story.published_at else None,
            period_start=_iso(story.period_start), period_end=_iso(story.period_end),
            period_precision=story.period_precision, period_label=_period(story),
            version=draft.version, body_html=sanitize_html(draft.content))
        # Explicit allowlist above deliberately excludes model, account and storage identifiers.
        budget += len(json.dumps(record, ensure_ascii=False).encode('utf-8'))
        if budget > MAX_TEXT_BYTES:
            abort(413, '本次正文较大，请返回导出页面按批次下载，本次未生成文件')
        records.append(record)
    stamp = datetime.datetime.now(ZoneInfo(Config.APP_TIMEZONE)).isoformat(timespec='seconds')
    info = dict(format_version=1, family_name=family.name, scope=scope, scope_label=SCOPE_LABELS[scope],
                exported_at=stamp, mode=mode, batch=batch if mode == 'batch' else None,
                article_count=len(records), eligible_total=total, batch_size=BATCH_SIZE,
                includes_media=False, includes_history=False,
                notes=['仅包含当前正文版本；不含照片、录音、小传、金句、评论、核实记录和历史版本。',
                       '历史时间未补造时区；故事时间以精度标记为准，区间边界不代表确切日。',
                       '分批导出以各次下载时的资料为准；期间有新增或变更时请重新核对各批。'])
    return records, info, revision_marks(rows, drafts)


def build_archive(records, info):
    html = render_template('article_export_offline.html', records=records, info=info).encode('utf-8')
    data = (json.dumps(dict(export=info, articles=records), ensure_ascii=False, indent=2)+'\n').encode('utf-8')
    readme = ('家音可读文章导出\n解压后打开 index.html 即可离线阅读，不需要登录或联网。\n'
              'articles.json 为结构化资料，manifest.json 列明范围、篇数和文件校验值。\n'
              '此包不含媒体或历史版本，不是完整家庭备份，也不是 AI 生成的电子书。\n'
              '下载副本不能远程撤回，请妥善保存，不要随意转发。\n' + '\n'.join(info['notes'])+'\n').encode('utf-8')
    files = {'index.html':html, 'articles.json':data, 'README.txt':readme}
    manifest = dict(info, files={name:{'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()} for name,content in files.items()})
    files['manifest.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2)+'\n').encode('utf-8')
    target = io.BytesIO()
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    target.seek(0)
    return target
