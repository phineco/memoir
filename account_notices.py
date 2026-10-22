"""Short-lived one-use server-side account results; no passwords in client sessions."""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
import time

from flask import current_app

TTL_SECONDS = 300


def _directory():
    namespace = hashlib.sha256(current_app.root_path.encode()).hexdigest()[:16]
    root = Path(current_app.config.get('ACCOUNT_NOTICE_DIR') or (Path(tempfile.gettempdir()) / ('memoir-notices-' + namespace)))
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.is_symlink() or root.stat().st_mode & 0o077:
        raise OSError('Private notice directory permissions required')
    return root


def _path(token):
    if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
        return None
    return _directory() / (token + '.json')


def cleanup():
    now=time.time()
    for path in _directory().glob('*.json'):
        if path.is_file() and path.stat().st_mtime < now-TTL_SECONDS:
            path.unlink(missing_ok=True)


def store(user_id, family_id, kind, data):
    cleanup()
    token=secrets.token_urlsafe(32)
    path=_path(token)
    fd=os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd,'w') as file:
        json.dump({'user':user_id,'family':family_id,'kind':kind,'expires':time.time()+TTL_SECONDS,'data':data},file)
    return token


def take(token, user_id, family_id, kind):
    path=_path(token)
    if path is None:
        return None
    try:
        fd=os.open(path,os.O_RDONLY | getattr(os,'O_NOFOLLOW',0))
        with os.fdopen(fd) as file:
            item=json.load(file)
        if item.get('expires',0)<time.time():
            path.unlink(missing_ok=True);return None
        if (item.get('user'),item.get('family'),item.get('kind')) != (user_id,family_id,kind):
            return None
        # Atomic claim across workers; only one reader can consume the result.
        claimed=path.with_name(path.name+'.'+secrets.token_hex(8)+'.claimed')
        path.rename(claimed)
        try:
            return item['data']
        finally:
            claimed.unlink(missing_ok=True)
    except (FileNotFoundError,ValueError,KeyError):
        return None


def revoke(token, user_id):
    path=_path(token)
    if path is None:return
    try:
        item=json.loads(path.read_text())
        if item.get('user')==user_id:path.unlink(missing_ok=True)
    except (FileNotFoundError,ValueError):
        pass
