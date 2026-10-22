"""Exercise real pooled connections against disposable database files."""
import time
from types import SimpleNamespace

import pytest
from sqlalchemy.pool import base as pool_base

import models
from app import create_app
from config import Config


@pytest.fixture
def persistent_app(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, 'DATABASE_URL', 'sqlite:///' + str(tmp_path / 'pool.db'))
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY='pool-regression-only')
    s = models.get_session()
    s.add_all([
        models.User(id='pool-owner', nickname='Pool Owner'),
        models.Family(id='pool-family', name='Preserved Family', owner_user_id='pool-owner'),
        models.FamilyMember(id='pool-member', family_id='pool-family', user_id='pool-owner', role='owner'),
    ])
    s.commit()
    models.remove_session()
    yield app
    models.remove_session()
    models._engine.dispose()


def test_help_recovers_when_an_idle_pooled_connection_is_closed(persistent_app):
    client = persistent_app.test_client()
    with client.session_transaction() as session:
        session['user_id'] = 'pool-owner'
    assert client.get('/guide?family_id=pool-family').status_code == 200
    assert not models._Session.registry.has()
    with models._engine.connect() as conn:
        stale_connection = conn.connection.driver_connection
    # Close after check-in: emulate a server killing an idle pooled connection.
    stale_connection.close()
    response = client.get('/guide?family_id=pool-family')
    assert response.status_code == 200
    assert '使用帮助' in response.get_data(as_text=True)
    assert not models._Session.registry.has()
    with models._engine.connect() as conn:
        assert conn.connection.driver_connection is not stale_connection
    assert models.get_session().query(models.Family).one().name == 'Preserved Family'


def test_memory_database_is_not_recycled_after_elapsed_time(app, monkeypatch):
    models.remove_session()
    now = time.time()
    # Advance only the pool's wall clock, without sleeps or changing app timestamps.
    monkeypatch.setattr(pool_base, 'time', SimpleNamespace(time=lambda: now + 7200))
    assert models.get_session().query(models.Family).filter_by(id='a').one().name == 'Alpha Family'
