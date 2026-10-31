import io
import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

import models
import interviewing as iv
import interview_audio as audio
import interview_asr as asr
import interview_materials as materials
import organize_preview
import organize_drafts
from models import InterviewClip,InterviewSession,InterviewAnswer,OrganizeRecord,Interview,get_session
from test_interview_asr import prepared
from backup import create_backup,restore_backup,verify_backup


def test_archive_delete_and_retry_preserve_story_but_revoke_sources(app,client,login,prepared,monkeypatch):
    sid,cid=prepared;s=get_session()
    asr.begin(s,'a','member-a',sid,cid,'asr-start-1',True)
    asr.run_one(lambda *args:('小时候在河边长大。',{}))
    row=iv.owned(s,'a','member-a',sid)
    iv.finish(s,'a','member-a',sid,row.revision);rid=row.record_id
    organize_preview.manual(s,'a','member-a',rid,1,0)
    story=organize_drafts.confirm(s,'a','member-a',rid,1,1,'draft-confirm');story_id=story.id
    archive=materials.export(s,'a','member-a',sid)
    with zipfile.ZipFile(archive) as bundle:
        assert 'audio/'+cid+'.wav' in bundle.namelist()
        data=json.loads(bundle.read('采访记录.json'))
        assert data['clips'][0]['original_transcript']=='小时候在河边长大。'
    archive.close()
    login('owner-a');path='/f/a/interview/'+sid
    assert client.get(path+'/export').status_code==404
    login('member-a');materials.request_delete(s,'a','member-a',sid)
    assert client.get(path+'/audio/'+cid).status_code in (404,410)
    assert client.get(path+'/export').status_code==410
    assert '小时候在河边长大。' not in client.get(path).get_data(as_text=True)
    assert s.get(OrganizeRecord,rid).del_flag==1 and not s.get(OrganizeRecord,rid).content and s.get(Interview,story_id)
    original=audio.delete
    monkeypatch.setattr(audio,'delete',lambda key:(_ for _ in ()).throw(RuntimeError('offline')))
    assert materials.purge_one()
    assert s.get(InterviewSession,sid).state=='delete_failed'
    assert not materials.purge_one()  # backoff, not a busy retry loop
    monkeypatch.setattr(audio,'delete',original)
    materials.retry(s,'a','member-a',sid);assert materials.purge_one()
    assert s.get(InterviewSession,sid).state=='deleted'
    assert not s.query(InterviewClip).count() and not s.query(InterviewAnswer).count()
    assert s.get(Interview,story_id)


def test_delete_during_transcription_discards_late_private_result(app,prepared):
    sid,cid=prepared;s=get_session();asr.begin(s,'a','member-a',sid,cid,'asr-start-1',True)
    def provider(*args):
        materials.request_delete(s,'a','member-a',sid)
        return '迟到的秘密转写',{}
    asr.run_one(provider)
    assert s.get(InterviewClip,cid).transcript is None
    assert not s.query(InterviewAnswer).count()
    assert materials.purge_one()


def test_backup_restores_interview_audio_transcript_and_correction_versions(app,prepared,tmp_path):
    sid,cid=prepared;s=get_session()
    asr.begin(s,'a','member-a',sid,cid,'asr-start-1',True);asr.run_one(lambda *args:('原始转写。',{}))
    row=iv.owned(s,'a','member-a',sid);answer=iv.answers(s,sid)[0]
    iv.edit_answer(s,'a','member-a',sid,row.revision,answer.id,1,'人工纠错。')
    key=s.get(InterviewClip,cid).storage_key;s.commit()
    source=tmp_path/'snapshot.db'
    connection=models._engine.raw_connection()
    try:
        with sqlite3.connect(source) as dest:connection.driver_connection.backup(dest)
    finally:connection.close()
    bundle=tmp_path/'backup.tar.gz'
    create_backup('sqlite:///'+str(source),bundle,Path(app.config['UPLOAD_DIR']))
    assert verify_backup(bundle)['engine']=='sqlite'
    restored=tmp_path/'restored.db';media=tmp_path/'restored-media'
    restore_backup('sqlite:///'+str(restored),bundle,media)
    with sqlite3.connect(restored) as db:
        assert db.execute('SELECT transcript FROM interview_clips WHERE id=?',(cid,)).fetchone()[0]=='原始转写。'
        content,history=db.execute('SELECT content,history FROM interview_answers WHERE id=?',(answer.id,)).fetchone()
        assert content=='人工纠错。' and json.loads(history)[0]['content']=='原始转写。'
    assert (media/key).read_bytes()[:4]==b'RIFF'


def test_individual_material_deletion_keeps_archive_explicit_and_full_delete_still_works(app,client,login,prepared):
    sid,cid=prepared;s=get_session()
    asr.begin(s,'a','member-a',sid,cid,'asr-start-1',True);asr.run_one(lambda *args:('独立采访原稿。',{}))
    row=iv.owned(s,'a','member-a',sid);iv.finish(s,'a','member-a',sid,row.revision);rid=row.record_id
    import organizing
    organizing.delete(s,'a','member-a',rid)
    login('member-a');html=client.get('/f/a/interview/'+sid).get_data(as_text=True)
    assert '整理原稿已删除' in html and '继续核对整理记录' not in html
    assert 'audio/'+cid in html
    from werkzeug.exceptions import HTTPException
    with pytest.raises(HTTPException):iv.finish(s,'a','member-a',sid,row.revision)
    s.rollback();materials.request_delete(s,'a','member-a',sid)
    assert materials.purge_one() and not s.query(InterviewClip).count()
