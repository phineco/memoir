import sqlite3

import pytest

from migrate import run_migrations


def old_database(tmp_path):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE users (id TEXT PRIMARY KEY, nickname TEXT)")
        db.execute("CREATE TABLE persons (id TEXT PRIMARY KEY, name TEXT, birth_year INTEGER, death_year INTEGER, birth_calendar TEXT, death_calendar TEXT)")
        db.execute("INSERT INTO persons VALUES ('old-person', 'Ancestor', 1940, 2001, 'lunar', 'solar')")
        db.execute("CREATE TABLE interviews (id TEXT PRIMARY KEY, create_date DATETIME, publish_status TEXT)")
        db.execute("INSERT INTO users VALUES ('old', 'preserved')")
    return path


def test_migration_dry_run_is_read_only_and_repeat_is_safe(tmp_path):
    path = old_database(tmp_path)
    url = "sqlite:///" + str(path)
    before = path.read_bytes()
    run_migrations(url, dry_run=True)
    assert path.read_bytes() == before
    run_migrations(url)
    run_migrations(url)
    with sqlite3.connect(path) as db:
        assert "name" in {r[1] for r in db.execute("PRAGMA table_info(users)")}
        assert db.execute("SELECT nickname FROM users WHERE id='old'").fetchone()[0] == "preserved"
        assert db.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 7


def test_missing_database_does_not_get_created_by_dry_run(tmp_path):
    path = tmp_path / "missing.db"
    with pytest.raises(ValueError):
        run_migrations("sqlite:///" + str(path), dry_run=True)
    assert not path.exists()


def test_failed_migration_not_marked_applied(tmp_path):
    path = old_database(tmp_path)
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "bad.sql").write_text("ALTER TABLE users ADD COLUMN extra TEXT; INVALID SQL;")
    with pytest.raises(Exception):
        run_migrations("sqlite:///" + str(path), migrations_dir=migrations)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 0
