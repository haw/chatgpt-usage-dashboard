from app.analytics import build_workspace_dashboard, detect_workspace_alerts


def usage(day: int, chat_tokens: int = 100, chat_dau: int = 5) -> dict:
    tokens = {"chat": chat_tokens, "codex": 20, "work": 10}
    return {
        "date": f"2026-09-{day:02d}",
        "end_date": f"2026-09-{day + 1:02d}",
        "active_users": {"chat": chat_dau, "codex": 3, "work": 1},
        "tokens": {**tokens, "total": sum(tokens.values())},
    }


def test_dashboard_does_not_sum_product_dau():
    result = build_workspace_dashboard([usage(1)], {"status": "success"})
    assert result["kpis"]["latest_max_product_dau"] == 5
    assert result["kpis"]["total_tokens"] == 130


def test_detects_token_spike_and_dau_drop_after_baseline():
    rows = [usage(day) for day in range(1, 8)]
    rows.append(usage(8, chat_tokens=1000, chat_dau=1))
    alerts = detect_workspace_alerts(rows)
    assert any(a["type"] == "token_spike" and a["product"] == "chat" for a in alerts)
    assert any(a["type"] == "dau_drop" and a["product"] == "chat" for a in alerts)


def test_selected_period_uses_period_wide_baseline_without_earlier_data():
    rows = [usage(day) for day in range(1, 8)]
    rows.append(usage(8, chat_tokens=1000))
    result = build_workspace_dashboard(
        rows, {"status": "success"}, "2026-09-08", "2026-09-08"
    )
    assert [row["date"] for row in result["daily"]] == ["2026-09-08"]
    assert result["kpis"]["total_tokens"] == 1030
    assert result["alerts"] == []
    assert result["available_period"] == {
        "start_date": "2026-09-01", "end_date": "2026-09-08"
    }
    point = result["analysis"][0]
    assert point["date"] == "2026-09-08"
    assert point["baseline"] == 1030
    assert point["threshold"] == 2060
    assert point["is_anomaly"] is False


def test_selected_period_detects_using_only_values_inside_period():
    rows = [usage(day) for day in range(1, 8)]
    rows.append(usage(8, chat_tokens=1000))
    result = build_workspace_dashboard(
        rows, {"status": "success"}, "2026-09-02", "2026-09-08"
    )
    point = result["analysis"][-1]
    assert point["baseline"] == 130
    assert point["threshold"] == 260
    assert point["is_anomaly"] is True
    assert any(alert["type"] == "token_spike" for alert in result["alerts"])
