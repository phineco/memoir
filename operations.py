"""Site operations permission is explicitly configured, never inferred from family role."""
from flask import abort, current_app


def is_operator(user):
    return bool(user and user.id in current_app.config.get('OPERATIONS_USER_IDS',()))


def require_operator(user):
    if not is_operator(user):abort(403)
