#!/usr/bin/env python3
"""Read-only preflight of application tables, columns and migration filenames."""
import json
from pathlib import Path
import sys

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import Config
from database_diagnostics import database_details
from models import Base


def check_database(url):
    parsed = make_url(url)
    backend = parsed.get_backend_name()
    if backend not in ('sqlite', 'mysql'):
        raise ValueError('unsupported_database')
    if backend == 'sqlite' and parsed.database in (None, '', ':memory:'):
        raise ValueError('persistent_database_required')
    if backend == 'sqlite' and not Path(parsed.database).is_file():
        raise ValueError('sqlite_file_missing')
    engine = create_engine(url, connect_args={'connect_timeout':5} if backend == 'mysql' else {})
    try:
        with engine.connect() as connection:
            inspector = inspect(connection)
            actual = set(inspector.get_table_names())
            missing_tables = sorted(set(Base.metadata.tables) - actual)
            missing_columns = {}
            for name, table in sorted(Base.metadata.tables.items()):
                if name not in actual:
                    continue
                columns = {column['name'] for column in inspector.get_columns(name)}
                missing = sorted(set(table.columns.keys()) - columns)
                if missing:
                    missing_columns[name] = missing
            history = 'schema_migrations' in actual
            history_columns = {column['name'] for column in inspector.get_columns('schema_migrations')} if history else set()
            history_valid = history and 'filename' in history_columns
            done = {row[0] for row in connection.execute(text('SELECT filename FROM schema_migrations'))} if history_valid else set()
            pending = sorted(path.name for path in (ROOT/'migrations').glob('*.sql') if path.name not in done)
            return dict(ready=not missing_tables and not missing_columns and history_valid and not pending,
                        database_backend=backend, missing_tables=missing_tables, missing_columns=missing_columns,
                        migration_history_valid=history_valid, pending_migrations=pending)
    finally:
        engine.dispose()


def main():
    try:
        result = check_database(Config.DATABASE_URL)
    except Exception as error:
        # No exception strings: even an invalid URL can contain credentials.
        details = database_details(error)
        result = dict(ready=False, check_failed=True, **details)
        if type(error) is ValueError and error.args in [('unsupported_database',),('persistent_database_required',),('sqlite_file_missing',)]:
            result['configuration_issue'] = error.args[0]
        print(json.dumps(result, ensure_ascii=False))
        print('检查失败；请核对网站同一虚拟环境、数据库配置及连接权限。不要发送连接串或密码。')
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result['ready']:
        print('数据库结构或迁移记录尚未就绪。先停网页/声音进程并备份，再用同一配置单进程执行 python migrate.py，之后重新检查。')
        print('若迁移提示已完成但仍缺表/列，请停止启动，核对是否连接同一数据库及迁移记录；不要删表或重新初始化已有库。')
        return 1
    print('表、字段与迁移记录检查通过；未执行建表、迁移或修改业务资料。此检查不代替运行和恢复验收。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
