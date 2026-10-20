#!/usr/bin/env python3
"""数据库增量迁移：一行命令补齐表结构，不用再手动拼 ALTER。

用法（项目目录下，用项目 venv 的 python）：
    python migrate.py            # 按 migrations/*.sql 顺序补齐未执行的
    python migrate.py --dry-run  # 只看会执行哪些，不动数据库

约定：
- migrations/ 下文件名按字典序执行（如 001_xxx.sql、002_xxx.sql），每个文件只执行一次，
  执行记录记在 schema_migrations 表里。
- 每个迁移文件的 SQL 写法兼容 MySQL 5.7 和 SQLite：
  - ALTER TABLE ... ADD COLUMN ... 语句若列已存在会自动跳过（migrate.py 预检），
    所以即使之前手动跑过同样的 ALTER，再跑一次也是安全的。
  - COMMENT '...' 只在 MySQL 生效，SQLite 下会自动去掉。
- 语句按分号切分；迁移文件里不要写存储过程/触发器这类带分号的复杂体。

服务器更新流程从此变成固定三步：
    git pull && <venv>/bin/python migrate.py && （面板重启项目）
以后再有表结构变更，只会多一个 migrations/00N_xxx.sql 文件，不用记零散的 ALTER。
"""

import os
import re
import sys
from pathlib import Path

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_MIGRATIONS_DIR = os.path.join(_BASE_DIR, "migrations")

sys.path.insert(0, _BASE_DIR)
from config import Config  # noqa: E402  (复用 .env / 环境变量的 DATABASE_URL 加载)

_ALTER_ADD_COL = re.compile(
    r"^\s*ALTER\s+TABLE\s+[`\"]?(\w+)[`\"]?\s+ADD\s+(?:COLUMN\s+)?[`\"]?(\w+)",
    re.IGNORECASE,
)
_COMMENT_CLAUSE = re.compile(r"\s+COMMENT\s+('[^']*'|\"[^\"]*\")", re.IGNORECASE)


def _dialect(url: str) -> str:
    return "sqlite" if url.startswith("sqlite") else "mysql"


def _connect(url: str):
    from sqlalchemy import create_engine, text
    eng = create_engine(url)
    conn = eng.connect()
    return eng, conn, text


def _ensure_migrations_table(conn, text, dialect: str):
    if dialect == "mysql":
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "filename varchar(255) PRIMARY KEY, "
            "applied_at datetime NOT NULL DEFAULT CURRENT_TIMESTAMP)"))
    else:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "filename TEXT PRIMARY KEY, "
            "applied_at TEXT NOT NULL DEFAULT (datetime('now')))"))
    conn.commit()


def _applied(conn, text) -> set:
    rows = conn.execute(text("SELECT filename FROM schema_migrations")).fetchall()
    return {r[0] for r in rows}


def _split_statements(sql: str):
    """按分号切分，跳过引号内的分号和 -- 注释行。"""
    stmts, buf = [], []
    quote = None
    i = 0
    while i < len(sql):
        ch = sql[i]
        if quote:
            buf.append(ch)
            if ch == quote and sql[i - 1] != "\\":
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            buf.append(ch)
        elif ch == "-" and sql[i:i + 2] == "--":
            while i < len(sql) and sql[i] != "\n":
                i += 1
        elif ch == ";":
            s = "".join(buf).strip()
            if s:
                stmts.append(s)
            buf = []
        else:
            buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        stmts.append(tail)
    return stmts


def _column_exists(conn, text, dialect: str, table: str, column: str) -> bool:
    if dialect == "mysql":
        n = conn.execute(
            text("SELECT COUNT(*) FROM information_schema.COLUMNS "
                 "WHERE TABLE_SCHEMA = DATABASE() "
                 "AND TABLE_NAME = :t AND COLUMN_NAME = :c"),
            {"t": table, "c": column}).scalar()
        return bool(n)
    rows = conn.execute(text("PRAGMA table_info(%s)" % table)).fetchall()
    return any(r[1] == column for r in rows)


def _adapt(stmt: str, dialect: str) -> str:
    if dialect == "sqlite":
        stmt = _COMMENT_CLAUSE.sub("", stmt)
    return stmt


def run_migrations(url, dry_run=False, migrations_dir=None):
    """可测试的迁移入口。预演只读，不创建数据库或迁移记录表。"""
    from sqlalchemy import inspect
    from sqlalchemy.engine import make_url

    dialect = _dialect(url)
    parsed = make_url(url)
    if parsed.get_backend_name() not in ("sqlite", "mysql"):
        raise ValueError("只支持 SQLite / MySQL")
    if dialect == "sqlite" and parsed.database not in (None, "", ":memory:") \
            and not Path(parsed.database).is_file():
        raise ValueError("数据库文件不存在；请先初始化，迁移不会创建空库")
    migrations_dir = migrations_dir or _MIGRATIONS_DIR
    files = sorted(f for f in os.listdir(migrations_dir)
                   if f.endswith(".sql"))
    if not files:
        print("migrations/ 下没有 .sql 文件，无事可做。")
        return 0

    eng, conn, text = _connect(url)
    try:
        if not dry_run:
            _ensure_migrations_table(conn, text, dialect)
        done = _applied(conn, text) if inspect(conn).has_table("schema_migrations") else set()
        pending = [f for f in files if f not in done]
        if not pending:
            print("数据库已是最新，无需迁移。")
            return 0
        for f in pending:
            path = Path(migrations_dir) / f
            stmts = _split_statements(path.read_text(encoding="utf-8"))
            print("== %s：%d 条语句" % (f, len(stmts)))
            for stmt in stmts:
                m = _ALTER_ADD_COL.match(stmt)
                if m:
                    table, column = m.group(1), m.group(2)
                    if _column_exists(conn, text, dialect, table, column):
                        print("   跳过（列已存在）: %s.%s" % (table, column))
                        continue
                if dry_run:
                    print("   [dry-run] %s" % stmt[:100])
                else:
                    conn.execute(text(_adapt(stmt, dialect)))
                    print("   执行: %s" % stmt[:100].replace("\n", " "))
            if not dry_run:
                conn.execute(
                    text("INSERT INTO schema_migrations (filename) VALUES (:f)"),
                    {"f": f})
                conn.commit()
                print("   已记录。")
        print("完成。" if not dry_run else "dry-run 结束，未改动数据库。")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
        eng.dispose()


def main() -> int:
    return run_migrations(Config.DATABASE_URL, dry_run="--dry-run" in sys.argv)


if __name__ == "__main__":
    sys.exit(main())
