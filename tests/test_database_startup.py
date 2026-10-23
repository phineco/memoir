"""Application workers must never create or change the database schema."""
import os
from pathlib import Path
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, inspect, text

from app import create_app
from config import Config
from init_db import initialize_database
from migrate import run_migrations
import models


def test_empty_database_initialization_and_migration_preserve_existing_data(tmp_path):
    url = "sqlite:///" + str(tmp_path / "new.db")
    initialize_database(url)
    engine = create_engine(url)
    try:
        assert set(inspect(engine).get_table_names()) == set(models.Base.metadata.tables)
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO users (id,nickname) VALUES ('kept','Preserved')"))
        with pytest.raises(ValueError, match="已有表"):
            initialize_database(url)
        run_migrations(url)
        run_migrations(url)
        with engine.connect() as conn:
            assert conn.execute(text("SELECT nickname FROM users WHERE id='kept'")).scalar_one() == "Preserved"
    finally:
        engine.dispose()


@pytest.mark.parametrize("backend", ["sqlite", "mysql"])
def test_application_startup_never_provisions_tables(tmp_path, monkeypatch, backend):
    url = ("sqlite:///" + str(tmp_path / "not-created.db") if backend == "sqlite"
           else "mysql+pymysql://unused@127.0.0.1:1/unused")
    monkeypatch.setattr(Config, "DATABASE_URL", url)

    def forbidden(*args, **kwargs):
        pytest.fail("An application worker attempted to create tables")

    monkeypatch.setattr(models.Base.metadata, "create_all", forbidden)
    application = create_app()
    assert application.test_client().get("/login").status_code == 200
    assert models._engine.pool._pre_ping
    if backend == "mysql":
        assert models._engine.pool._recycle == Config.DB_POOL_RECYCLE_SECONDS
    assert not (tmp_path / "not-created.db").exists()


def test_concurrent_workers_leave_missing_table_for_migration(tmp_path):
    path = tmp_path / "workers.db"
    url = "sqlite:///" + str(path)
    engine = create_engine(url)
    models.Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (id,nickname) VALUES ('kept','Preserved')"))
    models.AiTurn.__table__.drop(engine)
    engine.dispose()
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, DATABASE_URL=url, DEEPSEEK_API_KEY="", PYTHONDONTWRITEBYTECODE="1")
    code = "from app import app; assert app.test_client().get('/login').status_code == 200"
    workers = []
    try:
        for _ in range(4):
            workers.append(subprocess.Popen([sys.executable, "-B", "-c", code], cwd=root,
                                            env=env, stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE, text=True))
        for worker in workers:
            stdout, stderr = worker.communicate(timeout=30)
            assert worker.returncode == 0, stdout + stderr
    finally:
        for worker in workers:
            if worker.poll() is None:
                worker.kill()
                worker.communicate()
    engine = create_engine(url)
    try:
        assert not inspect(engine).has_table("ai_turns")
        run_migrations(url)
        run_migrations(url)
        assert inspect(engine).has_table("ai_turns")
        with engine.connect() as conn:
            assert conn.execute(text("SELECT nickname FROM users WHERE id='kept'")).scalar_one() == "Preserved"
            assert conn.execute(text("SELECT COUNT(*) FROM schema_migrations")).scalar_one() == len(list((root / "migrations").glob("*.sql")))
    finally:
        engine.dispose()
