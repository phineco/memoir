import ai
import models
from models import Family, get_session


def test_normal_requests_release_database_session(client, login):
    login()
    assert client.get("/f/a").status_code == 200
    assert not models._Session.registry.has()


def test_stream_keeps_context_until_complete_then_releases_session(client, login, monkeypatch):
    login()
    monkeypatch.setattr(ai, "ai_enabled", lambda: True)
    def stream(*args, **kwargs):
        yield get_session().query(Family).filter_by(id="a").one().name
    monkeypatch.setattr(ai, "chat_stream", stream)
    response = client.post("/f/a/ask/stream", json={"message": "hello"})
    assert "Alpha Family" in response.get_data(as_text=True)
    response.close()
    assert not models._Session.registry.has()
