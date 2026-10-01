from fastapi.testclient import TestClient

from app.web import app


HEADER = "Start Time,End Time,Chat,Codex,Work\n"


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
