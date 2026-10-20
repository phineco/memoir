import io
import json
from pathlib import Path
import sqlite3
import tarfile

import pytest

from backup import (BackupError, _mysql_options, create_backup, main,
                    restore_backup, verify_backup)


@pytest.fixture
def archive_source(tmp_path):
    source = tmp_path / "source.db"
    media = tmp_path / "photos"
    (media / "a/pa").mkdir(parents=True)
    (media / "a/pa/old.png").write_bytes(b"family-photo-bytes")
    conn = sqlite3.connect(source)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE photos (id TEXT, storage_path TEXT, del_flag INTEGER)")
    conn.execute("INSERT INTO photos VALUES ('p', 'a/pa/old.png', 0)")
    conn.execute("CREATE TABLE drafts (version INTEGER, content TEXT)")
    conn.executemany("INSERT INTO drafts VALUES (?, ?)", [(1, "original story"), (2, "corrected story")])
    conn.execute("CREATE TABLE schema_migrations (filename TEXT)")
    conn.execute("INSERT INTO schema_migrations VALUES ('001_add_users_name.sql')")
    conn.commit()
    # 保持连接打开，确保备份覆盖尚在 WAL 内的已提交数据。
    yield source, media
    conn.close()


def test_backup_verify_and_restore_preserve_wal_versions_and_photos(tmp_path, archive_source):
    source, media = archive_source
    archive = tmp_path / "snapshot.tar.gz"
    create_backup("sqlite:///" + str(source), archive, media)
    manifest = verify_backup(archive)
    assert manifest["engine"] == "sqlite"
    assert archive.stat().st_mode & 0o777 == 0o600
    restored = tmp_path / "restored.db"
    restored_media = tmp_path / "restored-media"
    restore_backup("sqlite:///" + str(restored), archive, restored_media)
    with sqlite3.connect(restored) as db:
        assert db.execute("SELECT content FROM drafts ORDER BY version").fetchall() == [("original story",), ("corrected story",)]
        assert db.execute("SELECT filename FROM schema_migrations").fetchone()[0] == "001_add_users_name.sql"
    assert (restored_media / "a/pa/old.png").read_bytes() == b"family-photo-bytes"
    assert main(["verify", str(archive)]) == 0


def test_restore_refuses_existing_database_and_media(tmp_path, archive_source):
    source, media = archive_source
    archive = tmp_path / "snapshot.tar.gz"
    create_backup("sqlite:///" + str(source), archive, media)
    before = source.read_bytes()
    with pytest.raises(BackupError):
        restore_backup("sqlite:///" + str(source), archive, tmp_path / "new-media")
    assert source.read_bytes() == before
    assert not (tmp_path / "new-media").exists()
    with pytest.raises(BackupError):
        restore_backup("sqlite:///" + str(tmp_path / "new.db"), archive, media)
    assert not (tmp_path / "new.db").exists()
    with pytest.raises(BackupError):
        create_backup("sqlite:///" + str(source), archive, media)


def test_missing_photo_aborts_backup(tmp_path, archive_source):
    source, media = archive_source
    (media / "a/pa/old.png").unlink()
    with pytest.raises(BackupError, match="未归档"):
        create_backup("sqlite:///" + str(source), tmp_path / "bad.tar.gz", media)
    assert not (tmp_path / "bad.tar.gz").exists()


def test_oss_requires_export_and_can_be_restored_for_reupload(tmp_path, archive_source):
    source, media = archive_source
    archive = tmp_path / "oss.tar.gz"
    with pytest.raises(BackupError, match="OSS"):
        create_backup("sqlite:///" + str(source), archive, media, "oss")
    create_backup("sqlite:///" + str(source), archive, media, "oss", oss_export=True)
    manifest = restore_backup("sqlite:///" + str(tmp_path / "oss.db"), archive, tmp_path / "oss-export")
    assert manifest["storage_backend"] == "oss"


def test_media_symlinks_are_not_archived(tmp_path, archive_source):
    source, media = archive_source
    secret = tmp_path / "private-env"
    secret.write_text("secret")
    (media / "leak").symlink_to(secret)
    with pytest.raises(BackupError, match="符号链接"):
        create_backup("sqlite:///" + str(source), tmp_path / "bad.tar.gz", media)


@pytest.mark.parametrize("name", ["../../outside", "/tmp/outside", "media/../escape"])
def test_archive_path_traversal_is_rejected(tmp_path, name):
    archive = tmp_path / "malicious.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        member = tarfile.TarInfo(name)
        member.size = 1
        bundle.addfile(member, io.BytesIO(b"x"))
    with pytest.raises(BackupError):
        verify_backup(archive)


def test_checksum_mismatch_is_rejected_before_restore(tmp_path, archive_source):
    source, media = archive_source
    archive = tmp_path / "snapshot.tar.gz"
    create_backup("sqlite:///" + str(source), archive, media)
    corrupt = tmp_path / "corrupt.tar.gz"
    with tarfile.open(archive, "r:gz") as src, tarfile.open(corrupt, "w:gz") as dst:
        for member in src:
            data = src.extractfile(member).read()
            if member.name.startswith("media/"):
                data = b"changed"
            member.size = len(data)
            dst.addfile(member, io.BytesIO(data))
    with pytest.raises(BackupError, match="校验失败"):
        restore_backup("sqlite:///" + str(tmp_path / "must-not-exist.db"), corrupt, tmp_path / "must-not-exist-media")
    assert not (tmp_path / "must-not-exist.db").exists()
    assert not (tmp_path / "must-not-exist-media").exists()


def test_mysql_credentials_only_live_in_private_temporary_file(tmp_path):
    with _mysql_options("mysql+pymysql://user:p%22ass@localhost/memoir", tmp_path) as (path, database):
        assert path.stat().st_mode & 0o777 == 0o600
        assert 'password="p\\"ass"' in path.read_text()
        assert database == "memoir"
    assert not path.exists()


def test_cli_does_not_fall_back_when_target_env_is_invalid(tmp_path, capsys):
    env = tmp_path / "restore.env"
    env.write_text("APP_ENV=local\n")
    assert main(["--env-file", str(env), "restore", "missing", "--media-dir", str(tmp_path / "new")]) == 1
    assert "DATABASE_URL" in capsys.readouterr().err


def test_cli_round_trip_with_separate_environment_files(tmp_path, archive_source):
    source, media = archive_source
    archive = tmp_path / "cli.tar.gz"
    source_env = tmp_path / "source.env"
    source_env.write_text(f"DATABASE_URL=sqlite:///{source}\nUPLOAD_DIR={media}\nSTORAGE_BACKEND=local\n")
    assert main(["--env-file", str(source_env), "create", "--output", str(archive)]) == 0
    target_env = tmp_path / "target.env"
    target_db = tmp_path / "cli-restored.db"
    target_env.write_text(f"DATABASE_URL=sqlite:///{target_db}\n")
    assert main(["--env-file", str(target_env), "restore", str(archive), "--media-dir", str(tmp_path / "cli-media")]) == 0
    with sqlite3.connect(target_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM drafts").fetchone()[0] == 2


def test_missing_source_database_is_not_created(tmp_path):
    source = tmp_path / "missing.db"
    with pytest.raises(BackupError):
        create_backup("sqlite:///" + str(source), tmp_path / "invalid.tar.gz", tmp_path / "media")
    assert not source.exists()
