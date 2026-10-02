import json

import pytest
from fastapi.testclient import TestClient

from app.web import app


HEADER = "Start Time,End Time,Chat,Codex,Work\n"


def analytics_json(kind, days, value=10):
    return json.dumps({
        "chart_key": kind,
        "series": [{"column": product} for product in ("Chat", "Codex", "Work")],
        "rows": [{"Start Time": day, "End Time": day, "Chat": value, "Codex": 0, "Work": 0}
                 for day in days],
    }).encode()


@pytest.mark.parametrize("first", ["tokens", "active-users"])
def test_single_json_is_analyzed_immediately_and_preserves_other_metric(tmp_path, monkeypatch, first):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    client = TestClient(app)
    second = "active-users" if first == "tokens" else "tokens"

    def upload(kind, days, value=10):
        response = client.post("/api/import", files=[
            ("files", ("arbitrary-name.json", analytics_json(kind, days, value), "application/json")),
        ])
        assert response.status_code == 200, response.text
        return response.json()

    first_metric = "active_users" if first == "active-users" else "tokens"
    second_metric = "tokens" if first == "active-users" else "active_users"
    initial = upload(first, ["2026-09-01", "2026-09-02"])
    assert len(initial["daily"]) == 2
    assert initial["daily"][0][first_metric]["chat"] == 10
    assert second_metric not in initial["daily"][0]
    assert initial["kpis"]["total_tokens"] == (20 if first == "tokens" else None)
    assert len(initial["analysis"]) == (2 if first == "tokens" else 0)
    history = client.get("/api/imports").json()["imports"]
    assert len(history) == 1
    assert history[0]["tokens_bytes" if first == "tokens" else "active_users_bytes"] > 0
    assert history[0]["active_users_bytes" if first == "tokens" else "tokens_bytes"] is None

    combined = upload(second, ["2026-09-02", "2026-09-03"], 5)
    assert len(combined["daily"]) == 3
    overlap = combined["daily"][1]
    assert overlap[first_metric]["chat"] == 10
    assert overlap[second_metric]["chat"] == 5
    updated = upload(first, ["2026-09-02"], 30)
    assert updated["daily"][1][first_metric]["chat"] == 30
    assert updated["daily"][1][second_metric]["chat"] == 5
    assert client.get("/api/dashboard").json()["daily"] == updated["daily"]
    isolated = client.get("/api/dashboard?start_date=2026-09-01&end_date=2026-09-01").json()
    assert len(isolated["daily"]) == 1
    assert isolated["kpis"]["total_tokens"] == (10 if first == "tokens" else None)


def test_json_batch_accepts_different_periods_and_validates_before_saving(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    client = TestClient(app)
    tokens = ("files", ("tokens.json", analytics_json("tokens", ["2026-09-01"]), "application/json"))
    invalid = ("files", ("bad.json", b'{"chart_key":"active-users"}', "application/json"))
    assert client.post("/api/import", files=[tokens, invalid]).status_code == 400
    assert client.get("/api/dashboard").json()["daily"] == []
    assert client.get("/api/imports").json()["imports"] == []
    active = ("files", ("active.json", analytics_json("active-users", ["2026-09-03"]), "application/json"))
    result = client.post("/api/import", files=[tokens, active])
    assert result.status_code == 200, result.text
    assert len(result.json()["daily"]) == 2
    assert result.json()["kpis"]["daily_average_tokens"] == 10
    assert client.get("/api/imports").json()["imports"][0]["days"] == 2


def test_detectors_endpoint_lists_configured_detectors():
    response = TestClient(app).get("/api/detectors")
    assert response.status_code == 200
    body = response.json()
    assert body["errors"] == []
    assert {d["id"] for d in body["detectors"]} >= {"token_spike", "dau_change"}
    assert all({"label", "description", "group", "scopes", "params"} <= set(d) for d in body["detectors"])


def test_dashboard_signals_carry_detector_and_severity(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    client = TestClient(app)
    days = [f"2026-09-{day:02d}" for day in range(1, 8)]
    files = [("files", ("tokens.json", analytics_json("tokens", days), "application/json"))]
    assert client.post("/api/import", files=files).status_code == 200
    files = [("files", ("tokens.json", analytics_json("tokens", ["2026-09-08"], 1000), "application/json"))]
    data = client.post("/api/import", files=files).json()
    assert data["kpis"]["alerts"] >= 1
    assert {alert["detector"] for alert in data["alerts"]} >= {"token_spike"}
    assert all(alert["severity"] in {"high", "medium", "info"} for alert in data["alerts"])
    assert [d["id"] for d in data["detectors"]] == [d["id"] for d in client.get("/api/detectors").json()["detectors"]]


def test_day_overrides_are_applied_from_query_and_form(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    client = TestClient(app)
    days = [f"2026-09-{day:02d}" for day in range(1, 8)]  # 9/5-9/6 are a weekend
    files = [("files", ("tokens.json", analytics_json("tokens", days), "application/json"))]
    data = client.post("/api/import", files=files, data={"holidays": "2026-09-01"}).json()
    kinds = {row["date"]: row["day_kind_source"] for row in data["daily"]}
    assert kinds["2026-09-01"] == "override" and kinds["2026-09-05"] == "weekend"
    data = client.get("/api/dashboard?workdays=2026-09-05").json()
    kinds = {row["date"]: (row["day_kind"], row["day_kind_source"]) for row in data["daily"]}
    assert kinds["2026-09-05"] == ("workday", "override") and kinds["2026-09-01"] == ("workday", "weekday")
    assert client.get("/api/dashboard?holidays=not-a-date").status_code == 400
    assert client.get("/api/individual?holidays=2026-09-01").status_code == 200


def test_context_endpoint_returns_rows_around_a_date(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    client = TestClient(app)
    days = [f"2026-09-{day:02d}" for day in range(1, 11)]
    files = [("files", ("tokens.json", analytics_json("tokens", days), "application/json"))]
    assert client.post("/api/import", files=files).status_code == 200
    body = client.get("/api/context?date=2026-09-08&before=3&after=1").json()
    assert [row["date"] for row in body["rows"]] == ["2026-09-05", "2026-09-06", "2026-09-07", "2026-09-08", "2026-09-09"]
    assert body["rows"][0]["day_kind"] == "holiday"  # Saturday
    assert client.get("/api/context?date=bad").status_code == 422


def test_index_has_four_views():
    response = TestClient(app).get("/")
    assert response.status_code == 200
    for view in ("triage", "workspace", "individual", "settings"):
        assert f'id="{view}-tab"' in response.text
    assert "インサイト" in response.text and "取込と設定" in response.text
    assert 'id="context-dialog"' in response.text
    assert 'id="triage-today"' in response.text and 'id="workspace-json-files"' in response.text
    assert 'id="settings-dialog"' in response.text
    assert 'id="individual-five-hour-hits"' in response.text
    assert 'id="individual-weekly-hits"' in response.text
    assert 'id="individual-weekly-table"' in response.text
    assert "5時間枠消費率" in response.text
    assert "週次枠消費率" in response.text
    assert response.text.count('id="history-dialog"') == 1
    assert 'id="history-table"' in response.text
    assert 'id="individual-history-table"' in response.text
    assert "全体データ" in response.text
    assert "個人データ" in response.text


def test_import_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    active = HEADER + "2026-09-01,2026-09-02,5,3,1\n"
    tokens = HEADER + "2026-09-01,2026-09-02,100,200,50\n"
    response = TestClient(app).post("/api/import", files={
        "active_users_file": ("active.csv", active, "text/csv"),
        "tokens_file": ("tokens.csv", tokens, "text/csv"),
    })
    assert response.status_code == 200
    assert response.json()["kpis"]["total_tokens"] == 350
    assert (tmp_path / "normalized" / "workspace-usage.jsonl").exists()


def test_import_endpoint_reports_validation_error(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    response = TestClient(app).post("/api/import", files={
        "active_users_file": ("active.csv", "wrong,columns\n1,2\n", "text/csv"),
        "tokens_file": ("tokens.csv", HEADER + "2026-09-01,2026-09-02,1,2,3\n", "text/csv"),
    })
    assert response.status_code == 400
    assert "列" in response.json()["detail"]


def test_dashboard_rejects_reversed_period(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    response = TestClient(app).get(
        "/api/dashboard?start_date=2026-09-10&end_date=2026-09-01"
    )
    assert response.status_code == 400
    assert "開始日" in response.json()["detail"]


def test_import_history_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    response = TestClient(app).get("/api/imports")
    assert response.status_code == 200
    assert response.json() == {"imports": []}


def test_individual_import_and_dashboard(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    tokens = HEADER + "2026-09-01,2026-09-02,100,200,50\n"
    client = TestClient(app)
    response = client.post(
        "/api/individual/import",
        data={"user_label": "user@example.com"},
        files={"tokens_file": ("tokens.csv", tokens, "text/csv")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["selected_user"]["user_label"] == "user@example.com"
    assert payload["kpis"]["total_tokens"] == 350
    user_id = payload["selected_user"]["user_id"]
    loaded = client.get(f"/api/individual?user_id={user_id}")
    assert loaded.status_code == 200
    assert loaded.json()["daily"][0]["tokens"]["codex"] == 200
    assert (tmp_path / "normalized" / "individual-usage.jsonl").exists()
    history = client.get("/api/individual/imports")
    assert history.status_code == 200
    assert history.json()["imports"][0]["user_label"] == "user@example.com"


def test_individual_import_requires_label(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    response = TestClient(app).post(
        "/api/individual/import",
        data={"user_label": "   "},
        files={"tokens_file": ("tokens.csv", HEADER + "2026-09-01,2026-09-02,1,2,3\n", "text/csv")},
    )
    assert response.status_code == 400
