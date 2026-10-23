"""CSRF protection for personal data controls and new state-changing forms."""
import hmac
import secrets

from flask import abort, request, session


def csrf_token():
    if '_csrf' not in session:session['_csrf']=secrets.token_urlsafe(32)
    return session['_csrf']


def require_csrf():
    supplied=request.form.get('csrf_token') or request.headers.get('X-CSRF-Token','')
    expected=session.get('_csrf','')
    if not expected or not isinstance(supplied,str) or len(supplied)>200 or not hmac.compare_digest(expected.encode(),supplied.encode()):
        abort(400,'页面已过期，请刷新后重试')
