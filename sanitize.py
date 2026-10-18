"""富文本 HTML 白名单清洗（防 XSS）。

写文章/改草稿的 Quill 输出在入库前必须过一遍 sanitize_html；
模板里继续用 |safe 渲染（已清洗）。
"""
import bleach
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
    "ul": ["class"], "ol": ["class"], "li": ["class"],  # ql-align-*/ql-indent-*
}
_CSS = CSSSanitizer(allowed_css_properties=[
    "color", "background-color", "font-size", "text-align",
])


def sanitize_html(html: str) -> str:
    if not html:
        return ""
    return bleach.clean(
        html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        css_sanitizer=_CSS,
        strip=True,  # 非法标签直接去掉（保留文字），不转义
    )
