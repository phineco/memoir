import json
import os
import sqlite3

import pytest

from backup import restore_backup
from tools.backup_job import fresh, run_job


def test_job_verifies_replica_records_success_and_restores_independently(tmp_path):
    source=tmp_path/'source.db';media=tmp_path/'media';media.mkdir()
    with sqlite3.connect(source) as conn:
        conn.execute('CREATE TABLE photos (storage_path TEXT,del_flag INT)')
        conn.execute('CREATE TABLE drafts (content TEXT)')
        conn.execute("INSERT INTO drafts VALUES ('preserved')")
    local=tmp_path/'local';replica=tmp_path/'replica';replica.mkdir(mode=0o700)
    state=run_job('sqlite:///'+str(source),media,local,replica)
    assert fresh(local) and state['status']=='succeeded'
    archive=replica/state['archive']
    assert archive.stat().st_mode&0o777==0o600
    restore_backup('sqlite:///'+str(tmp_path/'restored.db'),archive,tmp_path/'restored-media')
    with sqlite3.connect(tmp_path/'restored.db') as conn:
        assert conn.execute('SELECT content FROM drafts').fetchone()[0]=='preserved'
    assert not fresh(local,0)


def test_failure_never_reports_success_or_deletes_old_backups(tmp_path):
    replica=tmp_path/'replica';replica.mkdir(mode=0o700)
    local=tmp_path/'local';local.mkdir(mode=0o700)
    old=local/'memoir-auto-20000101T000000Z-1234abcd.tar.gz';old.write_bytes(b'keep')
    os.utime(old,(1,1))
    with pytest.raises(Exception):
        run_job('sqlite:///'+str(tmp_path/'missing.db'),tmp_path/'media',local,replica)
    assert json.loads((local/'status.json').read_text())['status']=='failed'
    assert not fresh(local) and old.read_bytes()==b'keep'


def test_missing_replica_mount_is_not_silently_created(tmp_path):
    with pytest.raises(ValueError):
        run_job('sqlite:///unused',tmp_path/'media',tmp_path/'local',tmp_path/'missing-replica')
    assert not (tmp_path/'missing-replica').exists()
