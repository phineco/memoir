"""富文本 HTML 白名单清洗（防 XSS）。

写文章/改草稿的 Quill 输出在入库前必须过一遍 sanitize_html；
模板里继续用 |safe 渲染（已清洗）。
"""
import bleach
import re
from bleach.css_sanitizer import CSSSanitizer

_ALLOWED_TAGS = [
    "p", "br", "h1", "h2", "h3",
    "strong", "em", "u", "s",
    "ul", "ol", "li", "blockquote", "pre",
    "span",
]
_ALLOWED_ATTRS = {
    "span": ["style", "class"],  # Quill 的颜色/字号走 span style
    "p": ["class"], "h1": ["class"], "h2": ["class"], "h3": ["class"],
    "ul": ["class"], "ol": ["class"], "li": ["class", "data-list"],  # ql-align-*/ql-indent-*
}
_CSS = CSSSanitizer(allowed_css_properties=[
    "color", "background-color", "font-size", "text-align",
])


def sanitize_html(html: str, family_id=None) -> str:
    if not html:
        return ""
    attributes=dict(_ALLOWED_ATTRS)
    if family_id:
        def image_attribute(tag,name,value):
            if name=='alt':return len(value)<=500
            return name=='src' and bool(re.fullmatch(r'/f/'+re.escape(family_id)+r'/album/[A-Za-z0-9_-]{1,64}/image',value))
        attributes['img']=image_attribute
    return bleach.clean(
        html,
        tags=_ALLOWED_TAGS+(["img"] if family_id else []),
        attributes=attributes,
        css_sanitizer=_CSS,
        strip=True,  # 非法标签直接去掉（保留文字），不转义
    )
