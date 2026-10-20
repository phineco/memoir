#!/usr/bin/env python3
"""数据库与媒体归档；恢复仅写入全新目标，永不覆盖现有数据。"""
import argparse
import contextlib
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
from urllib.parse import quote

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError


class BackupError(Exception):
    pass


def _digest(path):
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _sqlite_path(url):
    path = make_url(url).database
    if not path or path == ":memory:":
        raise BackupError("备份和恢复要求磁盘数据库")
    return Path(path).resolve()


def _readonly_sqlite(path):
    return sqlite3.connect("file:" + quote(str(path), safe="/") + "?mode=ro", uri=True)


@contextlib.contextmanager
def _mysql_options(url, workdir):
    parsed = make_url(url)
    if not parsed.database or not re.fullmatch(r"[A-Za-z0-9_]+", parsed.database):
        raise BackupError("MySQL 数据库名须为字母、数字或下划线")
    if set(parsed.query) - {"charset"}:
        raise BackupError("URL 含原生客户端未适配的连接选项，请使用已验证的数据库原生备份方案")
    def escaped(value):
        return str(value or "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")
    config = Path(workdir) / "mysql-client.cnf"
    descriptor = os.open(config, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        handle.write("[client]\n")
        for name, value in [("host", parsed.host or "localhost"), ("port", parsed.port or 3306),
                            ("user", parsed.username), ("password", parsed.password),
                            ("default-character-set", "utf8mb4")]:
            handle.write(f'{name}="{escaped(value)}"\n')
    try:
        yield config, parsed.database
    finally:
        config.unlink(missing_ok=True)


def _native_mysql(program, url, workdir, output=None, source=None):
    executable = shutil.which(program)
    if not executable:
        raise BackupError(f"缺少 {program}，请安装与服务器版本匹配的 MySQL 客户端")
    with _mysql_options(url, workdir) as (config, database):
        command = [executable, f"--defaults-file={config}"]
        if program == "mysqldump":
            command += ["--single-transaction", "--skip-lock-tables", "--hex-blob"]
        command.append(database)
        try:
            subprocess.run(command, stdin=source, stdout=output or subprocess.DEVNULL,
                           stderr=subprocess.PIPE, check=True, timeout=3600)
        except (subprocess.SubprocessError, OSError):
            # 不把原生客户端错误原样输出，避免凭据或敏感 SQL 进入日志。
            raise BackupError(f"{program} 执行失败；请核对客户端版本、权限和连接配置") from None


def _snapshot_database(url, stage):
    engine_name = make_url(url).get_backend_name()
    if engine_name == "sqlite":
        source = _sqlite_path(url)
        if not source.is_file():
            raise BackupError("源数据库不存在")
        target = stage / "database.sqlite"
        with contextlib.closing(_readonly_sqlite(source)) as src, \
                contextlib.closing(sqlite3.connect(target)) as dest:
            src.backup(dest)
            if dest.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise BackupError("SQLite 完整性检查失败")
        return engine_name, target
    if engine_name == "mysql":
        target = stage / "database.sql"
        with target.open("wb") as output:
            _native_mysql("mysqldump", url, stage, output=output)
        return engine_name, target
    raise BackupError("只支持 SQLite / MySQL")


def _photo_keys(url):
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            if not inspect(conn).has_table("photos"):
                return []
            return [r[0] for r in conn.execute(text(
                "SELECT storage_path FROM photos WHERE del_flag = 0 AND storage_path IS NOT NULL"))]
    finally:
        engine.dispose()


def _copy_media(media_dir, stage):
    dest = stage / "media"
    dest.mkdir()
    if not media_dir.exists():
        return
    if not media_dir.is_dir() or media_dir.is_symlink():
        raise BackupError("媒体源必须是普通目录")
    for path in media_dir.rglob("*"):
        if path.is_symlink():
            raise BackupError("媒体目录含符号链接，拒绝越界归档")
        if path.is_file():
            target = dest / path.relative_to(media_dir)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)


def create_backup(url, archive, media_dir, storage_backend="local", oss_export=False):
    archive = Path(archive).resolve()
    media_dir = Path(media_dir).resolve()
    if storage_backend not in ("local", "oss"):
        raise BackupError("未知存储后端")
    if storage_backend == "oss" and (not oss_export or not media_dir.is_dir()):
        raise BackupError("OSS 必须先导出对象，再用 --media-dir 提供完整导出目录")
    if archive == media_dir or media_dir in archive.parents:
        raise BackupError("备份不能写入被归档的媒体目录")
    if archive.exists():
        raise BackupError("备份文件已存在，拒绝覆盖")
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="memoir-backup-", dir=archive.parent) as directory:
        stage = Path(directory)
        engine_name, database = _snapshot_database(url, stage)
        _copy_media(media_dir, stage)
        # SQLite 从刚生成的快照读取引用，包含 WAL 中已提交的数据。
        keys = _photo_keys("sqlite:///" + str(database) if engine_name == "sqlite" else url)
        for key in keys:
            relative = PurePosixPath(key)
            if relative.is_absolute() or ".." in relative.parts or not (stage / "media" / key).is_file():
                raise BackupError("存在未归档的照片引用，备份不完整；请核对媒体目录")
        manifest = {"format": 1, "engine": engine_name, "database": database.name,
                    "storage_backend": storage_backend,
                    "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "files": {p.relative_to(stage).as_posix(): _digest(p)
                              for p in stage.rglob("*") if p.is_file()}}
        (stage / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        created = False
        try:
            descriptor = os.open(archive, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created = True
            with os.fdopen(descriptor, "wb") as output, tarfile.open(fileobj=output, mode="w:gz") as bundle:
                for path in sorted(stage.rglob("*")):
                    if path.is_file():
                        bundle.add(path, arcname=path.relative_to(stage).as_posix(), recursive=False)
        except Exception:
            if created:
                archive.unlink(missing_ok=True)
            raise
    return manifest


def _unpack_verified(archive, stage):
    seen = set()
    try:
        with tarfile.open(archive, "r:gz") as bundle:
            for member in bundle:
                name = PurePosixPath(member.name)
                if not member.isfile() or name.is_absolute() or ".." in name.parts \
                        or member.name in seen or "\\" in member.name:
                    raise BackupError("归档含越界路径、重复文件或非普通文件")
                seen.add(member.name)
                dest = stage / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                with bundle.extractfile(member) as source, dest.open("xb") as target:
                    shutil.copyfileobj(source, target)
        manifest = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("format") != 1 or manifest.get("engine") not in ("sqlite", "mysql") \
                or manifest.get("storage_backend") not in ("local", "oss"):
            raise BackupError("不支持的备份格式")
        expected_db = "database.sqlite" if manifest["engine"] == "sqlite" else "database.sql"
        if manifest.get("database") != expected_db:
            raise BackupError("数据库归档名无效")
        files = manifest["files"]
        if not isinstance(files, dict) or expected_db not in files or set(files) != seen - {"manifest.json"}:
            raise BackupError("归档文件清单不一致")
        for name, digest in files.items():
            if name != expected_db and not name.startswith("media/"):
                raise BackupError("清单包含未知文件")
            if _digest(stage / name) != digest:
                raise BackupError("备份校验失败，文件可能损坏")
        if manifest["engine"] == "sqlite":
            with contextlib.closing(_readonly_sqlite(stage / expected_db)) as conn:
                if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise BackupError("SQLite 完整性检查失败")
        return manifest
    except (tarfile.TarError, OSError, ValueError, KeyError, TypeError,
            AttributeError, EOFError, sqlite3.DatabaseError):
        raise BackupError("备份无法读取或格式损坏") from None


def verify_backup(archive):
    with tempfile.TemporaryDirectory(prefix="memoir-verify-") as directory:
        return _unpack_verified(archive, Path(directory))


def restore_backup(url, archive, media_dir):
    media_dir = Path(media_dir).resolve()
    # 既有目录即拒绝，防止把恢复数据混入生产目录。
    if media_dir.exists():
        raise BackupError("媒体目标已存在；请使用全新目录")
    with tempfile.TemporaryDirectory(prefix="memoir-restore-") as directory:
        stage = Path(directory)
        manifest = _unpack_verified(archive, stage)
        engine_name = make_url(url).get_backend_name()
        if engine_name != manifest["engine"]:
            raise BackupError("备份和目标数据库类型不同，不提供跨引擎转换")
        database = stage / manifest["database"]
        target = None
        if engine_name == "sqlite":
            target = _sqlite_path(url)
            if target.exists():
                raise BackupError("目标数据库已存在；请使用全新文件")
            if target == media_dir or media_dir in target.parents:
                raise BackupError("目标数据库不能放在媒体目录内")
        else:
            engine = create_engine(url)
            try:
                if inspect(engine).get_table_names() or inspect(engine).get_view_names():
                    raise BackupError("MySQL 目标库非空；请先创建独立空库")
            finally:
                engine.dispose()
        media_dir.parent.mkdir(parents=True, exist_ok=True)
        # 先复制媒体；数据库失败时删除本次创建的媒体，既有数据不受影响。
        media_dir.mkdir(mode=0o700)
        created_database = False
        try:
            for path in (stage / "media").rglob("*"):
                if path.is_file():
                    dest = media_dir / path.relative_to(stage / "media")
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(path, dest)
            if engine_name == "sqlite":
                target.parent.mkdir(parents=True, exist_ok=True)
                descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                created_database = True
                with os.fdopen(descriptor, "wb") as output, database.open("rb") as source:
                    shutil.copyfileobj(source, output)
            else:
                with database.open("rb") as source:
                    _native_mysql("mysql", url, stage, source=source)
        except Exception:
            # MySQL 原生导入可能部分完成；保留目标库供诊断，重试换一个空库。
            shutil.rmtree(media_dir)
            if created_database:
                target.unlink(missing_ok=True)
            raise
        return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", help="独立部署/恢复环境文件；不会打包或回显凭据")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--output", required=True)
    create.add_argument("--media-dir", help="OSS 导出目录，或覆盖本地 UPLOAD_DIR")
    verify = sub.add_parser("verify")
    verify.add_argument("archive")
    restore = sub.add_parser("restore")
    restore.add_argument("archive")
    restore.add_argument("--media-dir", required=True, help="全新媒体恢复目录")
    args = parser.parse_args(argv)
    try:
        if args.command == "verify":
            verify_backup(args.archive)
        else:
            from config import Config
            values = {}
            if args.env_file:
                from dotenv import dotenv_values
                if not Path(args.env_file).is_file():
                    raise BackupError("环境文件不存在")
                values = dotenv_values(args.env_file)
                if not values.get("DATABASE_URL"):
                    raise BackupError("独立环境文件必须显式配置 DATABASE_URL")
            url = values.get("DATABASE_URL") or Config.DATABASE_URL
            if args.command == "create":
                storage = values.get("STORAGE_BACKEND") or (
                    ("oss" if values["APP_ENV"] == "cloud" else "local")
                    if "APP_ENV" in values else Config.STORAGE_BACKEND)
                media = args.media_dir or values.get("UPLOAD_DIR") or Config.UPLOAD_DIR
                create_backup(url, args.output, media, storage, oss_export=bool(args.media_dir))
            else:
                manifest = restore_backup(url, args.archive, args.media_dir)
                if manifest["storage_backend"] == "oss":
                    print("OSS 对象已恢复到媒体目录；需上传到独立私有桶并配置后再验收。")
        print("完成。")
        return 0
    except BackupError as error:
        import sys
        print(str(error), file=sys.stderr)
        return 1
    except (OSError, ValueError, SQLAlchemyError):
        import sys
        print("操作失败；请检查文件路径与连接配置（未回显凭据）。", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
