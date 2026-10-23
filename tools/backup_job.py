#!/usr/bin/env python3
"""One scheduled backup, verified replica and freshness check; installs no jobs."""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backup import create_backup, verify_backup
from config import Config


def _private_directory(path,create=False):
    path=Path(path)
    if path.is_symlink():raise ValueError('备份目录不能为符号链接')
    if create:path.mkdir(parents=True,exist_ok=True,mode=0o700)
    if not path.is_dir() or path.stat().st_mode & 0o077:
        raise ValueError('备份目录必须已存在且仅运行账号可访问')
    return path.resolve()


def _write_status(root,data):
    temp=root/('.status-'+secrets.token_hex(8))
    try:
        with os.fdopen(os.open(temp,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600),'w') as file:
            json.dump(data,file);file.flush();os.fsync(file.fileno())
        os.replace(temp,root/'status.json')
    finally:temp.unlink(missing_ok=True)


def fresh(root,max_hours=30):
    try:
        state=json.loads((Path(root)/'status.json').read_text())
        at=dt.datetime.fromisoformat(state['last_success'])
        age=(dt.datetime.now(dt.timezone.utc)-at).total_seconds()/3600
        return state['status']=='succeeded' and 0<=age<=max_hours
    except (OSError,ValueError,KeyError,TypeError):return False


def run_job(url,media_dir,output_dir,replica_dir,storage='local',oss_export=False,keep_days=30):
    if keep_days<1:raise ValueError('保留天数必须为正整数')
    root=_private_directory(output_dir,create=True)
    lockfd=os.open(root/'.job.lock',os.O_CREAT|os.O_WRONLY,0o600)
    with os.fdopen(lockfd,'w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        previous={}
        try:previous=json.loads((root/'status.json').read_text())
        except (OSError,ValueError):pass
        now=dt.datetime.now(dt.timezone.utc)
        state=dict(status='running',attempted_at=now.isoformat(),last_success=previous.get('last_success'))
        _write_status(root,state)
        try:
            replica=_private_directory(replica_dir)
            if root==replica or root in replica.parents or replica in root.parents:
                raise ValueError('副本目录必须与本地目录独立')
            name='memoir-auto-'+now.strftime('%Y%m%dT%H%M%SZ')+'-'+secrets.token_hex(4)+'.tar.gz'
            archive=root/name;copy=replica/name
            create_backup(url,archive,media_dir,storage,oss_export)
            verify_backup(archive)
            with archive.open('rb') as source,os.fdopen(os.open(copy,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600),'wb') as target:
                shutil.copyfileobj(source,target);target.flush();os.fsync(target.fileno())
            verify_backup(copy)
            def digest(path):
                hasher=hashlib.sha256()
                with path.open('rb') as file:
                    for block in iter(lambda:file.read(1024*1024),b''):hasher.update(block)
                return hasher.hexdigest()
            if digest(archive)!=digest(copy):raise ValueError('副本校验失败')
            cutoff=now.timestamp()-keep_days*86400
            for directory in (root,replica):
                for path in directory.iterdir():
                    if re.fullmatch(r'memoir-auto-\d{8}T\d{6}Z-[0-9a-f]{8}\.tar\.gz',path.name) and not path.is_symlink() and path.is_file() and path.stat().st_mtime<cutoff:
                        path.unlink()
            state.update(status='succeeded',last_success=dt.datetime.now(dt.timezone.utc).isoformat(),archive=name,sha256=digest(archive))
            _write_status(root,state)
            return state
        except Exception:
            state['status']='failed';_write_status(root,state)
            raise


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',required=True)
    parser.add_argument('--replica-dir')
    parser.add_argument('--media-dir')
    parser.add_argument('--keep-days',type=int,default=30)
    parser.add_argument('--check-age-hours',type=float)
    args=parser.parse_args(argv)
    if args.check_age_hours is not None:
        return 0 if args.check_age_hours>0 and fresh(args.output_dir,args.check_age_hours) else 1
    if not args.replica_dir:parser.error('--replica-dir is required for a backup')
    try:
        state=run_job(Config.DATABASE_URL,args.media_dir or Config.UPLOAD_DIR,args.output_dir,args.replica_dir,
                      Config.STORAGE_BACKEND,bool(args.media_dir),args.keep_days)
        print(json.dumps(state));return 0
    except Exception:
        print('备份未完成；请检查受限目录、媒体导出、数据库和异地挂载，未回显凭据。',file=sys.stderr)
        return 1


if __name__=='__main__':raise SystemExit(main())
