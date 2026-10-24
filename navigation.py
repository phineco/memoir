"""Explicit page ownership and local, permission-checked navigation context."""
import re
from urllib.parse import parse_qsl, urlencode, urlsplit

from flask import request, url_for


GROUPS = {
    'people': ('家人', 'main.family_home'),
    'stories': ('故事', 'main.stories'),
    'album': ('相册', 'album.index'),
    'more': ('更多', 'main.family_more'),
}
PAGES = {}
for group, entries in {
    'people': {
        'family_home': '家人', 'person_page': '人物详情', 'tree_add': '添加人物',
        'tree_edit': '编辑人物', 'portrait_edit': '编辑小传',
        'timeline_add': '添加人生事件', 'timeline_edit': '编辑人生事件',
        'family_manage': '家庭管理',
    },
    'stories': {
        'stories': '故事', 'story_detail': '故事详情', 'write_article': '写故事',
        'edit_article': '编辑故事', 'story_history': '历次版本', 'my_drafts': '我的草稿',
    },
    'more': {
        'family_more': '更多', 'ai_ask': '问 AI', 'plan_list': '写作计划',
        'plan_new': '新建写作计划', 'plan_edit': '编辑写作计划',
        'weekly_current': '本周周报', 'weekly_report': '周报', 'ebook_preview': '生成电子书',
        'article_export': '导出文章', 'sync_import': '同步入库', 'share_list': '分享管理',
        'share_preview': '分享预览',
    },
}.items():
    for endpoint, title in entries.items():
        PAGES['main.' + endpoint] = (group, title)
for endpoint, title in {
    'index': '家庭相册', 'detail': '照片详情', 'upload': '上传照片', 'edit': '编辑照片资料',
}.items():
    PAGES['album.' + endpoint] = ('album', title)
PAGES['voices.manage'] = ('people', '声音管理')
for endpoint, title in {
    'main.account': '个人中心', 'main.account_drafts': '我的草稿',
    'main.account_stories': '我的故事与记录', 'main.account_ai_memory': '我的 AI 记忆',
    'main.account_article_exports': '导出我的文章', 'main.display_preferences': '显示设置',
    'voices.my_voices': '我的声音', 'main.guide': '帮助', 'main.terms': '用户服务协议',
    'main.privacy': '隐私政策', 'main.index': '选择家庭', 'main.family_new': '创建家庭',
}.items():
    PAGES[endpoint] = (None, title)


def context(family=None):
    from views import _current_user, _families_for_user, _is_admin
    me = _current_user()
    families = _families_for_user(me) if me else []
    group, title = PAGES.get(request.endpoint, (None, ''))
    if request.endpoint and request.endpoint.startswith('privacy.'):
        title = '隐私申请'
    if request.endpoint and request.endpoint.startswith('metrics.'):
        title = '运营工作区'
    return dict(group=group, title=title, families=families,
                admin=bool(family and _is_admin(family, me)),
                links=[dict(key=key, label=label, href=url_for(endpoint, family_id=family.id))
                       for key, (label, endpoint) in GROUPS.items()] if family else [])


def safe_return(value, family_id=None):
    """Only rendered GET destinations in this family or personal lists are valid."""
    if not value or len(value) > 2048 or any(ord(c) < 32 for c in value) or '\\' in value:
        return None
    try:
        parts = urlsplit(value)
    except ValueError:
        return None
    if parts.scheme or parts.netloc or parts.path.startswith('//'):
        return None
    match = re.fullmatch(r'/f/([^/]+)(?:/(?:stories|album|person/[^/]+|story/[^/]+))?', parts.path)
    if match:
        if match[1] != str(family_id):
            return None
    elif parts.path not in ('/account', '/account/stories', '/account/drafts'):
        return None
    # Foreign navigation context must not be restored from a personal list either.
    for key, val in parse_qsl(parts.query):
        if key == 'family_id' and val != str(family_id):
            from flask import has_request_context
            if not has_request_context():return None
            from views import _current_user
            from models import get_session
            from access import family_role
            user=_current_user()
            if not user or not family_role(get_session(),val,user.id):return None
    return value


def back_url(default):
    fid = (request.view_args or {}).get('family_id') or request.args.get('family_id')
    return safe_return(request.args.get('return_to', ''), fid) or default


def return_label(default):
    fid=(request.view_args or {}).get('family_id') or request.args.get('family_id')
    target=safe_return(request.args.get('return_to',''),fid)
    if not target:return default
    path=urlsplit(target).path
    if path.startswith('/account/'):return '返回我的内容'
    if '/album' in path:return '返回家庭相册'
    if '/person/' in path:return '返回人物'
    if '/story/' in path or path.endswith('/stories'):return '返回故事'
    return '返回家人'


def context_link(target):
    parts = urlsplit(target)
    fid = (request.view_args or {}).get('family_id') or request.args.get('family_id')
    source = request.full_path.rstrip('?')
    # Preserve the parent detail's own return path; safe_return bounds nesting length.
    if not safe_return(source, fid):
        return target
    query = [(k, v) for k, v in parse_qsl(parts.query) if k != 'return_to']
    query.append(('return_to', source))
    return parts._replace(query=urlencode(query)).geturl()
