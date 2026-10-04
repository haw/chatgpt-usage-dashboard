from app.analytics import build_workspace_dashboard, detect_workspace_alerts
from app.detectors.stats import ratio_threshold


def test_missing_metrics_are_not_zero_or_baseline_samples():
    rows = [usage(day) for day in range(1, 9)]
    for row in rows[:7]:
        del row["active_users"]
    rows[-1]["tokens"] = {"chat": 1000, "codex": 0, "work": 0, "total": 1000}
    result = build_workspace_dashboard(rows, {})
    assert any(alert["type"] == "token_spike" for alert in result["alerts"])
    assert not any(alert["type"].startswith("dau") for alert in result["alerts"])
    assert result["products"][0]["average_active_users"] == 5
    zero = {"date": "2026-09-09", "tokens": {"chat": 0, "codex": 0, "work": 0, "total": 0}}
    result = build_workspace_dashboard([zero], {})
    assert result["kpis"]["total_tokens"] == 0
    assert result["kpis"]["latest_max_product_dau"] is None
    assert result["analysis"][0]["value"] == 0


def test_missing_days_do_not_extend_rolling_baseline_beyond_window():
    # 2026-09-30 is a Wednesday; only 4 workdays (9/2-9/4, 9/7) fall inside its 28-day window
    rows = [usage(day) for day in range(1, 8)] + [usage(30, chat_tokens=1000)]
    # today is pinned: with the real date the stale-data notice appears once 9/30 is more than 3 days old
    result = build_workspace_dashboard(rows, {}, today="2026-09-30")
    assert result["analysis"][-1]["baseline"] is None
    assert result["pending_days"] >= 1
    assert not [alert for alert in result["alerts"] if alert["date"] == "2026-09-30"]


def test_rows_carry_day_kind_and_overrides_apply():
    rows = [usage(day) for day in range(1, 8)]
    result = build_workspace_dashboard(rows, {})
    kinds = {row["date"]: (row["day_kind"], row["day_kind_source"]) for row in result["daily"]}
    assert kinds["2026-09-05"] == ("holiday", "weekend")
    assert kinds["2026-09-01"] == ("workday", "weekday")
    result = build_workspace_dashboard(rows, {}, day_overrides={"2026-09-01": "holiday"})
    assert [row for row in result["daily"] if row["date"] == "2026-09-01"][0]["day_kind_source"] == "override"


def test_holiday_baseline_uses_only_holidays():
    # Weekends get 100 chat tokens, workdays 1000. A Sunday with 3000 would be an ordinary jump for a
    # workday baseline that already holds a 3000-token day; against the other weekends it stands out.
    rows = []
    for day in range(1, 29):
        weekend = (day + 1) % 7 in (0, 6)  # 2026-09-05 (day 5) is Saturday
        rows.append(usage(day, chat_tokens=100 if weekend else 1000, chat_dau=1 if weekend else 5))
    rows[-1]["tokens"] = {"chat": 1000, "codex": 20, "work": 10, "total": 1030}  # 2026-09-28 is a Monday
    rows.append(usage(27, chat_tokens=3000, chat_dau=1))  # Sunday 9/27 far above every other weekend
    rows = sorted({row["date"]: row for row in rows}.values(), key=lambda row: row["date"])
    result = build_workspace_dashboard(rows, {}, today="2026-09-28")
    spikes = {(a["date"], a["product"]) for a in result["alerts"] if a["type"] == "token_spike"}
    assert ("2026-09-27", "chat") in spikes
    assert ("2026-09-28", "chat") not in spikes
    sunday = next(a for a in result["alerts"] if a["type"] == "token_spike" and a["date"] == "2026-09-27" and a["product"] == "chat")
    assert sunday["baseline"] == 100  # the other weekends, not the workdays


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
    # a single day is its own baseline; the line is 3.5 minimum spreads above it on the ratio scale
    assert point["threshold"] == round(ratio_threshold(1030, 0.25, 1030, 3.5), 1)
    assert point["is_anomaly"] is False


def test_selected_period_detects_using_only_values_inside_period():
    rows = [usage(day) for day in range(1, 8)]
    rows.append(usage(8, chat_tokens=1000))
    result = build_workspace_dashboard(
        rows, {"status": "success"}, "2026-09-02", "2026-09-08"
    )
    point = result["analysis"][-1]
    assert point["baseline"] == 130
    assert point["threshold"] == round(ratio_threshold(130, 0.25, 130, 3.5), 1)
    assert point["is_anomaly"] is True
    assert any(alert["type"] == "token_spike" for alert in result["alerts"])
