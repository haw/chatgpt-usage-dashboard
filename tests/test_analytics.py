from app.analytics import build_dashboard


def usage(date: str, user: str, value: float) -> dict:
    return {"date": date, "user_id": user, "user_name": user,
            "product": "chatgpt", "activity": value, "metrics": {}}


def test_dashboard_totals_and_spike_detection():
    rows = [usage("2026-09-01", "u1", 10), usage("2026-09-02", "u1", 12),
            usage("2026-09-03", "u1", 50), usage("2026-09-01", "u2", 5)]
    result = build_dashboard(rows, {"status": "success"})

    assert result["kpis"]["active_users"] == 2
    assert result["kpis"]["total_activity"] == 77
    assert any(alert["type"] == "spike" and alert["user_id"] == "u1" for alert in result["alerts"])

