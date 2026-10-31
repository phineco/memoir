"""Versioned human preview. Changing a quote into a paraphrase changes its label."""
import copy

from flask import abort

from models import OrganizeRecord
from organizing import owned
from reporting import local_now


def guard(s, fid, uid, rid, source_revision, preview_revision):
    record = owned(s, fid, uid, rid, lock=True)
    if record.story_id or str(record.revision) != str(source_revision) or str(record.preview_revision) != str(preview_revision):
        abort(409, '原稿或预览已变化，请核对较新版本；当前编辑未覆盖。')
    return record


def store(s, record, data):
    changed = s.query(OrganizeRecord).filter_by(id=record.id, revision=record.revision,
        preview_revision=record.preview_revision, story_id=None).update({OrganizeRecord.preview: data,
        OrganizeRecord.preview_revision: record.preview_revision + 1,
        OrganizeRecord.preview_source_revision: record.revision, OrganizeRecord.update_date: local_now()}, synchronize_session=False)
    if changed != 1:
        s.rollback()
        abort(409, '另一窗口已修改，请核对后再保存。')
    s.commit()
    s.refresh(record)
    return record


def manual(s, fid, uid, rid, source_revision, preview_revision):
    record = guard(s, fid, uid, rid, source_revision, preview_revision)
    return store(s, record, dict(title=record.topic or '我的回忆', body=record.content,
        quotes=[], verification=[], timeline=[], people=[], period=None))


def save(s, fid, uid, rid, source_revision, preview_revision, data):
    record = guard(s, fid, uid, rid, source_revision, preview_revision)
    if not record.preview or record.preview_source_revision != record.revision:
        abort(409, '请先基于当前原稿准备预览。')
    result = copy.deepcopy(record.preview)
    for name, limit in [('title', 128), ('body', 30000)]:
        value = data.get(name)
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            abort(400, '请填写标题和正文，标题最多128字，正文最多30000字。')
        result[name] = value.strip()
    for key in ('quotes', 'verification', 'timeline', 'people'):
        rows = []
        for i, row in enumerate(result[key]):
            if data.get('keep_'+key+'_'+str(i)) != 'yes':
                continue
            if key == 'quotes':
                value = data.get('quote_'+str(i), row['text'])
                if not isinstance(value, str) or not value.strip() or len(value) > 500:
                    abort(400, '原话或摘要最多500字，删除请取消勾选。')
                row['text'] = value.strip()
                row['kind'] = 'quote' if row['text'] in row['evidence'] and row['text'] in record.content else 'summary'
            rows.append(row)
        result[key] = rows
    if data.get('keep_period') != 'yes':
        result['period'] = None
    return store(s, record, result)
