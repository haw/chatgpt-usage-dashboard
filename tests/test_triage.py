import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.detectors import build_detector_set
from app.triage import build_triage
from app.web import app
from tests.test_new_detectors import load_fixture_rows

CONFIG = Path(__file__).parent.parent / "config" / "detectors.toml"


def test_triage_ranks_the_multi_detector_day_first_and_separates_tiers():
    rows = load_fixture_rows()
    result = build_triage(rows, {"completed_at": "2026-10-02T00:00:00+00:00"}, build_detector_set(CONFIG), [],
                          today="2026-10-02")
    assert result["status"]["latest_date"] == "2026-10-01" and result["status"]["stale"] is False
    assert result["today"], "expected at least one day to review today"
    dates = [e["date"] for e in result["today"]]
    assert "2026-10-01" in dates[:3], dates
    top = next(e for e in result["today"] if e["date"] == "2026-10-01")
    assert top["detectors"] >= 2 and top["max_severity"] == "high" and not top["continuing"]
    assert len(result["today"]) <= 5
    # a day that only continues the previous days' pattern ranks below the onset day
    scores = {e["date"]: e["score"] for tier in ("today", "week", "reference") for e in result[tier]}
    assert scores["2026-09-23"] < scores["2026-09-21"]
    assert all(e["observations"] for e in result["today"] + result["week"] + result["reference"])
    assert all(e["tier"] == "reference" for e in result["reference"])
    # stale_data is reported as panel status, never as an observation
    assert not any(o["detector"] == "stale_data" for e in result["today"] + result["week"] + result["reference"]
                   for o in e["observations"])
    stale = build_triage(rows, {}, build_detector_set(CONFIG), [], today="2026-10-20")
    assert stale["status"]["stale"] is True and stale["status"]["age_days"] == 19


def test_explained_days_drop_to_reference_and_latest_disposition_wins():
    rows = load_fixture_rows()
    detectors = build_detector_set(CONFIG)
    dispositions = [
        {"date": "2026-10-01", "kind": "escalate", "note": "", "recorded_at": "2026-10-02T01:00:00+00:00"},
        {"date": "2026-10-01", "kind": "explained", "note": "負荷試験", "recorded_at": "2026-10-02T02:00:00+00:00"},
    ]
    result = build_triage(rows, {}, detectors, dispositions, today="2026-10-02")
    entry = next(e for tier in ("today", "week", "reference") for e in result[tier] if e["date"] == "2026-10-01")
    assert entry["tier"] == "reference" and entry["disposition"]["note"] == "負荷試験"
    assert not result["today"] or result["today"][0]["date"] != "2026-10-01"


def test_observations_carry_novelty_and_streak():
    rows = load_fixture_rows()
    result = build_triage(rows, {}, build_detector_set(CONFIG), [], today="2026-10-02")
    entries = {e["date"]: e for tier in ("today", "week", "reference") for e in result[tier]}
    holidays = [entries[d] for d in ("2026-09-21", "2026-09-22", "2026-09-23") if d in entries]
    assert holidays, "inferred holidays should appear"
    first = min(holidays, key=lambda e: e["date"])
    assert any(o["novel"] for o in first["observations"])
    streaks = [o["streak"] for e in holidays for o in e["observations"] if o["detector"] == "holiday_usage"]
    assert max(streaks) >= 2


def test_disposition_api_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    client = TestClient(app)
    assert client.post("/api/dispositions", json={"date": "2026-09-01", "kind": "bogus"}).status_code == 400
    assert client.post("/api/dispositions", json={"date": "not-a-date", "kind": "explained"}).status_code == 400
    response = client.post("/api/dispositions", json={"date": "2026-09-01", "kind": "explained", "note": "  全社  研修 "})
    assert response.status_code == 200
    assert response.json()["disposition"]["note"] == "全社 研修"
    stored = (tmp_path / "normalized" / "dispositions.jsonl").read_text().splitlines()
    assert len(stored) == 1 and json.loads(stored[0])["kind"] == "explained"
    triage = client.get("/api/triage")
    assert triage.status_code == 200
    assert triage.json()["status"]["latest_date"] is None
