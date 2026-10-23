import json

import pytest
from sqlalchemy import create_engine, inspect, text

from app import create_app
from config import Config
from migrate import run_migrations
import models
from tools.check_database import check_database, main


def current_database(tmp_path):
    path = tmp_path/'schema.db'
    url = 'sqlite:///'+str(path)
    engine = create_engine(url)
    models.Base.metadata.create_all(engine)
    engine.dispose()
    run_migrations(url)
    return path, url


def test_preflight_reads_actual_columns_without_changing_a_current_database(tmp_path):
    path, url = current_database(tmp_path)
    before = path.read_bytes()
    result = check_database(url)
    assert result['ready'] and not result['pending_migrations']
    assert path.read_bytes() == before
    engine=create_engine(url)
    with engine.begin() as conn:
        conn.execute(text('ALTER TABLE family_visits RENAME COLUMN guide_status TO legacy_guide_status'))
    engine.dispose()
    before=path.read_bytes()
    result=check_database(url)
    assert not result['ready'] and not result['pending_migrations']
    assert result['missing_columns']=={'family_visits':['guide_status']}
    assert path.read_bytes()==before  # A migration history row is not proof of the actual structure.


def test_missing_sqlite_file_is_never_created(tmp_path):
    path=tmp_path/'absent.db'
    with pytest.raises(ValueError,match='sqlite_file_missing'):
        check_database('sqlite:///'+str(path))
    assert not path.exists()


def test_missing_progress_table_is_reproduced_then_fixed_by_migration(tmp_path,monkeypatch):
    path=tmp_path/'deployed.db';url='sqlite:///'+str(path)
    engine=create_engine(url)
    models.Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (id,nickname,del_flag) VALUES ('kept','Preserved user',0)"))
        conn.execute(text("INSERT INTO families (id,name,owner_user_id,del_flag) VALUES ('kept-family','Preserved family','kept',0)"))
        conn.execute(text("INSERT INTO interviews (id,family_id,author_id,topic,publish_status,visibility,del_flag) VALUES ('kept-story','kept-family','kept','Preserved story','published','public',0)"))
        conn.execute(text("INSERT INTO drafts (id,interview_id,version,is_current,content,del_flag) VALUES ('kept-draft','kept-story',1,1,'<p>Preserved body</p>',0)"))
    models.FamilyVisit.__table__.drop(engine);engine.dispose()
    monkeypatch.setattr(Config,'DATABASE_URL',url)
    application=create_app();application.config.update(TESTING=True,SECRET_KEY='test-only')
    client=application.test_client()
    with client.session_transaction() as state:state['user_id']='kept'
    assert client.get('/f/kept-family/stories').status_code==500
    result=check_database(url)
    assert result['missing_tables']==['family_visits']
    assert '010_family_visits.sql' in result['pending_migrations']
    engine=create_engine(url)
    assert 'family_visits' not in inspect(engine).get_table_names()
    engine.dispose()
    run_migrations(url)
    assert check_database(url)['ready']
    response=client.get('/f/kept-family/stories')
    assert response.status_code==200 and 'Preserved story' in response.get_data(as_text=True)
    s=models.get_session()
    assert s.query(models.User).filter_by(id='kept').one().nickname=='Preserved user'
    assert s.query(models.Draft).filter_by(id='kept-draft').one().content=='<p>Preserved body</p>'
    models._Session.remove();models._engine.dispose()


def test_cli_does_not_print_connection_credentials(monkeypatch,capsys):
    monkeypatch.setattr(Config,'DATABASE_URL','mysql+PRIVATE_DRIVER://PRIVATE_USER:PRIVATE_PASSWORD@PRIVATE_HOST/PRIVATE_DB')
    assert main()==2
    output=capsys.readouterr().out
    assert 'PRIVATE_' not in output and json.loads(output.splitlines()[0])['check_failed']
