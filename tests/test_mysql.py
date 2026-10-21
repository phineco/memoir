"""仅在显式配置的测试服务上创建随机临时库；不接触项目 DATABASE_URL。"""
import os
from pathlib import Path
import shutil
import uuid

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from backup import create_backup, restore_backup, verify_backup
from migrate import _split_statements, run_migrations
from models import Draft, Family, Interview, Photo, User
from person_dates import DATE_FIELDS


pytestmark = pytest.mark.skipif(
    not os.environ.get("MEMOIR_TEST_MYSQL_ADMIN_URL"),
    reason="未配置独立 MySQL 测试服务；由 CI 的 MySQL 作业执行",
)


def test_mysql_schema_migration_and_native_backup_restore(tmp_path):
    admin_url = make_url(os.environ["MEMOIR_TEST_MYSQL_ADMIN_URL"])
    assert admin_url.get_backend_name() == "mysql"
    if not shutil.which("mysql") or not shutil.which("mysqldump"):
        pytest.fail("MySQL 集成测试要求原生 mysql / mysqldump 客户端")
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    prefix = "memoir_test_" + uuid.uuid4().hex[:12]
    source_name, target_name = prefix + "_source", prefix + "_restore"
    created = []
    engines = []
    try:
        with admin.connect() as conn:
            for name in (source_name, target_name):
                conn.execute(text(f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4"))
                created.append(name)
        source_url = admin_url.set(database=source_name).render_as_string(hide_password=False)
        target_url = admin_url.set(database=target_name).render_as_string(hide_password=False)
        source = create_engine(source_url)
        engines.append(source)
        schema = (Path(__file__).resolve().parents[1] / "memoir-mysql-schema.sql").read_text()
        with source.begin() as conn:
            for statement in _split_statements(schema):
                conn.execute(text(statement))
        assert len(inspect(source).get_table_names()) == 28
        with source.begin() as conn:
            for field in DATE_FIELDS:
                conn.execute(text(f"ALTER TABLE persons DROP COLUMN {field}"))
            conn.execute(text("INSERT INTO persons (id,name,birth_year,death_year,birth_calendar,death_calendar) VALUES ('old-person','Ancestor',1940,2001,'lunar','solar')"))
        run_migrations(source_url, dry_run=True)
        assert not inspect(source).has_table("schema_migrations")
        run_migrations(source_url)
        run_migrations(source_url)
        with source.connect() as conn:
            row=conn.execute(text("SELECT birth_lunar_year,birth_solar_year,death_solar_year FROM persons WHERE id='old-person'")).one()
            assert tuple(row)==(1940,None,2001)
        with sessionmaker(bind=source)() as session:
            session.add(User(id="u", nickname="history"))
            session.add(Family(id="f", name="Family history", owner_user_id="u"))
            session.add(Interview(id="i", family_id="f", topic="A life", publish_status="published"))
            session.add_all([Draft(id="d1", interview_id="i", version=1, content="first"),
                             Draft(id="d2", interview_id="i", version=2, content="corrected", is_current=True)])
            session.add(Photo(id="p", family_id="f", storage_path="f/p.png"))
            session.commit()
        media = tmp_path / "media"
        (media / "f").mkdir(parents=True)
        (media / "f/p.png").write_bytes(b"old-photo")
        archive = tmp_path / "mysql.tar.gz"
        create_backup(source_url, archive, media)
        assert verify_backup(archive)["engine"] == "mysql"
        restore_backup(target_url, archive, tmp_path / "restored-media")
        restored = create_engine(target_url)
        engines.append(restored)
        with restored.connect() as conn:
            assert conn.execute(text("SELECT content FROM drafts ORDER BY version")).scalars().all() == ["first", "corrected"]
            assert conn.execute(text("SELECT COUNT(*) FROM schema_migrations")).scalar_one() == 2
        assert (tmp_path / "restored-media/f/p.png").read_bytes() == b"old-photo"
        assert len(inspect(restored).get_table_names()) == 29
    finally:
        for engine in engines:
            engine.dispose()
        with admin.connect() as conn:
            for name in created:
                conn.execute(text(f"DROP DATABASE `{name}`"))
        admin.dispose()
