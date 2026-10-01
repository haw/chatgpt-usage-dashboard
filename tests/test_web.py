from fastapi.testclient import TestClient

from app.web import app


HEADER = "Start Time,End Time,Chat,Codex,Work\n"


def test_index_has_workspace_and_individual_tabs():
    response = TestClient(app).get("/")
    assert response.status_code == 200
    assert "全体分析" in response.text
    assert "個人別分析" in response.text
    assert 'id="settings-dialog"' in response.text
    assert 'id="individual-five-hour-hits"' in response.text
    assert 'id="individual-weekly-hits"' in response.text
    assert 'id="individual-weekly-table"' in response.text
    assert "5時間枠消費率" in response.text
    assert "週次枠消費率" in response.text
    assert 'id="individual-history-dialog"' in response.text


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
