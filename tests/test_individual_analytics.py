from app.analytics import build_individual_dashboard


def test_individual_dashboard_selects_user_and_aggregates_products():
    rows = [
        {"user_id": "u1", "user_label": "Alice", "date": "2026-09-01", "tokens": {"chat": 10, "codex": 20, "work": 5, "total": 35}},
        {"user_id": "u1", "user_label": "Alice", "date": "2026-09-02", "tokens": {"chat": 15, "codex": 25, "work": 0, "total": 40}},
        {"user_id": "u2", "user_label": "Bob", "date": "2026-09-01", "tokens": {"chat": 100, "codex": 0, "work": 0, "total": 100}},
    ]
    result = build_individual_dashboard(rows, {"status": "success"}, "u1")
    assert result["selected_user"]["user_label"] == "Alice"
    assert result["kpis"]["total_tokens"] == 75
    assert result["product_totals"] == {"chat": 25, "codex": 45, "work": 5}
    assert len(result["daily"]) == 2
    assert [user["user_label"] for user in result["users"]] == ["Alice", "Bob"]
