"""SQLite ignores SELECT FOR UPDATE: take its writer gate before owner reads."""
from sqlalchemy import text


def serialize_sqlite(s,user_id):
    if s.get_bind().dialect.name=='sqlite':
        with s.no_autoflush:
            s.execute(text('UPDATE users SET id=id WHERE id=:uid'),{'uid':user_id})
