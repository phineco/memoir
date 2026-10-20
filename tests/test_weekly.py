import datetime

import pytest

import ai
import reporting
from models import AiCache, Interview, NewPerson, ShareSnapshot, SyncLog, get_session


@pytest.fixture
def years(app):
    s = get_session()
    s.query(Interview).filter_by(id="public-a").one().create_date = datetime.datetime(2026, 10, 12)
    s.add(Interview(id="old-story", family_id="a", topic="old year", publish_status="published", visibility="public", create_date=datetime.datetime(2025, 10, 13)))
    for year, month, day in [(2025, 10, 13), (2026, 10, 12)]:
        s.add(NewPerson(id=f"new-{year}", family_id="a", name=f"person-{year}", create_date=datetime.datetime(year, month, day)))
        s.add(SyncLog(id=f"fail-{year}", family_id="a", status="failed", client_id=f"failure-{year}", create_date=datetime.datetime(year, month, day)))
    s.commit()


def test_api_separates_same_week_across_years(client, login, years):
    login()
    for year, expected in [(2025, "old-story"), (2026, "public-a")]:
        data = client.get(f"/api/weekly-report?family_id=a&year={year}&week=42").get_json()
        assert data["year"] == year
        assert data["week"] == 42
        assert expected in {story["id"] for story in data["stories"]}
        assert ("old-story" if year == 2026 else "public-a") not in {story["id"] for story in data["stories"]}
        assert data["new_persons"][0]["name"] == f"person-{year}"
        assert data["unsynced_count"] == 1


def test_iso_year_boundary_includes_december_dates(client, login, app):
    s = get_session()
    s.add(Interview(id="boundary", family_id="a", topic="December in next ISO year", visibility="public", publish_status="published", create_date=datetime.datetime(2024, 12, 30)))
    s.commit()
    login()
    data = client.get("/api/weekly-report?family_id=a&year=2025&week=1").get_json()
    assert "boundary" in {st["id"] for st in data["stories"]}


@pytest.mark.parametrize("query", ["year=bad&week=42", "year=2026&week=0", "year=2026&week=54", "year=2025&week=53", "year=0&week=1", "year=2026&week=no"])
def test_invalid_period_returns_400(client, login, query):
    login()
    assert client.get("/api/weekly-report?family_id=a&" + query).status_code == 400


def test_legacy_urls_and_canonical_year_links(client, login, years, monkeypatch):
    monkeypatch.setattr(reporting, "current_period", lambda: (2026, 42))
    login()
    assert client.get("/f/a/weekly/42").status_code == 200
    assert client.get("/f/a/weekly/42?year=2025").status_code == 200
    body = client.get("/f/a/weekly/2025/42").get_data(as_text=True)
    assert "2025 年第 42 周" in body
    assert "year=2025" in body


def test_ai_cache_has_year_and_ignores_ambiguous_legacy_rows(app, monkeypatch):
    s = get_session()
    s.add(AiCache(id="legacy", family_id="a", cache_key="weekly:a:42", content='{"digest":"ambiguous"}'))
    s.commit()
    assert ai.get_weekly_summary("a", 42, year=2026) is None
    monkeypatch.setattr(ai, "_chat_complete", lambda *a, **kw: '{"digest":"new", "highlights":[]}')
    ai.summarize_weekly("a", 42, {"year": 2026}, year=2026)
    assert ai.get_weekly_summary("a", 42, year=2026)["digest"] == "new"
    assert ai.get_weekly_summary("a", 42, year=2025) is None
    assert s.query(AiCache).filter_by(cache_key="weekly:a:42").one().content == '{"digest":"ambiguous"}'


def test_weekly_pages_keep_private_items_out_of_shared_api(client, login, app):
    s = get_session()
    s.add(NewPerson(id="secret-person", family_id="a", name="Secret Mention", interview_id="private-a"))
    s.commit()
    login("member-a")
    data = client.get("/api/weekly-report?family_id=a").get_json()
    assert "quote-private-a" not in data["quotes"]
    assert "Secret Mention" not in str(data)


def test_generate_historical_summary_keeps_requested_year(client, login, years, monkeypatch):
    login()
    monkeypatch.setattr(ai, "ai_enabled", lambda: True)
    monkeypatch.setattr(ai, "_chat_complete", lambda *a, **kw: '{"digest":"historical", "highlights":[]}')
    response = client.post("/f/a/weekly/2025/42/ai-summary")
    assert response.status_code == 302
    assert response.location.endswith("/weekly/2025/42")
    assert ai.get_weekly_summary("a", 42, year=2025)["digest"] == "historical"
    assert ai.get_weekly_summary("a", 42, year=2026) is None


def test_share_snapshot_uses_the_same_iso_year_as_report(client, login, years, monkeypatch):
    import views
    monkeypatch.setattr(views, "current_period", lambda: (2025, 42))
    login()
    assert client.post("/f/a/shares/new").status_code == 302
    snapshot = get_session().query(ShareSnapshot).one()
    assert snapshot.status == "draft"
    assert snapshot.content_json["year"] == 2025
    assert snapshot.content_json["week"] == 42
    assert [story["title"] for story in snapshot.content_json["stories"]] == ["old year"]
