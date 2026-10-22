"""Public invite URLs and local QR generation, independent of proxy Host headers."""
from io import BytesIO
from urllib.parse import urlsplit, urlunsplit


def public_base_url(value):
    value = value.strip()
    try:
        parts = urlsplit(value)
        port = parts.port  # Validate the port without inheriting any request headers.
    except ValueError:
        raise ValueError('PUBLIC_BASE_URL 必须是有效的公开站点地址') from None
    if (parts.scheme not in ('http', 'https') or not parts.hostname
            or parts.username is not None or parts.password is not None
            or parts.path not in ('', '/') or parts.query or parts.fragment
            or any(char.isspace() for char in value)):
        raise ValueError('PUBLIC_BASE_URL 只能包含协议和域名，例如 https://family.scyllatech.cn')
    return urlunsplit((parts.scheme, parts.netloc, '', '', ''))


def qr_png(url):
    import segno
    output = BytesIO()
    segno.make_qr(url, error='m').save(output, kind='png', scale=8, border=4,
                                     dark='black', light='white')
    return output.getvalue()


def public_url(endpoint, **values):
    """Every link intended for forwarding uses the configured public origin."""
    from flask import current_app, url_for
    values.pop('_external', None)
    return current_app.config['PUBLIC_BASE_URL'] + url_for(endpoint, _external=False, **values)
