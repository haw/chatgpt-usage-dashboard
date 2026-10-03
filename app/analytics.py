from __future__ import annotations

from typing import Any

from app.detectors import DetectionContext, DetectorSet, build_detector_set
from app.detectors.calendar import classify_days


PRODUCTS = ("chat", "codex", "work")


def default_detectors() -> DetectorSet:
    from app.config import Settings

    settings = Settings.from_env()
    return build_detector_set(settings.detectors_config, settings.plugins_dir)


def build_individual_dashboard(
    rows: list[dict[str, Any]],
    state: dict[str, Any],
    user_id: str | None = None,
    detectors: DetectorSet | None = None,
    day_overrides: dict[str, str] | None = None,
    sensitivity: float = 1.0,
) -> dict[str, Any]:
    detectors = detectors or default_detectors()
    users_by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        current = users_by_id.setdefault(row["user_id"], {
            "user_id": row["user_id"], "user_label": row["user_label"],
            "start_date": row["date"], "end_date": row["date"], "days": 0, "total_tokens": 0,
        })
        current["start_date"] = min(current["start_date"], row["date"])
        current["end_date"] = max(current["end_date"], row["date"])
        current["days"] += 1
        current["total_tokens"] += row["tokens"]["total"]
    users = sorted(users_by_id.values(), key=lambda item: item["user_label"].casefold())
    selected_id = user_id if user_id in users_by_id else (users[0]["user_id"] if users else None)
    daily = sorted((row for row in rows if row["user_id"] == selected_id), key=lambda row: row["date"])
    days = classify_days(daily, day_overrides, infer=False)
    ctx = DetectionContext(rows=daily, scope="individual", day_kinds={d: v["kind"] for d, v in days.items()},
                           sensitivity=sensitivity)
    analysis = detectors.series(ctx)
    alerts = detectors.run(ctx)
    daily = _with_day_kinds(daily, days)
    total = sum(row["tokens"]["total"] for row in daily)
    product_totals = {product: sum(row["tokens"][product] for row in daily) for product in PRODUCTS}
    return {
        "state": state,
        "users": users,
        "selected_user": users_by_id.get(selected_id),
        "daily": daily,
        "analysis": analysis,
        "alerts": alerts,
        "detectors": detectors.describe(),
        "detector_errors": detectors.errors,
        "product_totals": product_totals,
        "kpis": {
            "total_tokens": total,
            "daily_average_tokens": round(total / len(daily)) if daily else 0,
            "latest_tokens": daily[-1]["tokens"]["total"] if daily else 0,
            "alerts": len(alerts),
        },
    }


def build_workspace_dashboard(
    rows: list[dict[str, Any]],
    state: dict[str, Any],
    start_date: str | None = None,
    end_date: str | None = None,
    detectors: DetectorSet | None = None,
    day_overrides: dict[str, str] | None = None,
    sensitivity: float = 1.0,
    today: str | None = None,
) -> dict[str, Any]:
    detectors = detectors or default_detectors()
    ordered = sorted(rows, key=lambda row: row["date"])
    days = classify_days(ordered, day_overrides)  # reference level uses every stored day
    selected = [
        row for row in ordered
        if (start_date is None or row["date"] >= start_date)
        and (end_date is None or row["date"] <= end_date)
    ]
    period_wide = start_date is not None or end_date is not None
    ctx = DetectionContext(rows=selected, scope="workspace", period_wide=period_wide,
                           day_kinds={d: v["kind"] for d, v in days.items()}, sensitivity=sensitivity, today=today)
    alerts = detectors.run(ctx)
    analysis = detectors.series(ctx)
    selected = _with_day_kinds(selected, days)
    token_rows = [row for row in selected if row.get("tokens") is not None]
    dau_rows = [row for row in selected if row.get("active_users") is not None]
    total_tokens = sum(row["tokens"]["total"] for row in token_rows)
    latest = dau_rows[-1] if dau_rows else None
    products = []
    for product in PRODUCTS:
        products.append({
            "product": product,
            "tokens": sum(row["tokens"][product] for row in token_rows) if token_rows else None,
            "average_active_users": round(
                sum(row["active_users"][product] for row in dau_rows) / len(dau_rows), 1
            ) if dau_rows else None,
        })
    return {
        "state": state,
        "kpis": {
            "latest_max_product_dau": max(latest["active_users"].values()) if latest else None,
            "total_tokens": total_tokens if token_rows else None,
            "daily_average_tokens": round(total_tokens / len(token_rows)) if token_rows else None,
            "alerts": len(alerts),
        },
        "daily": selected,
        "products": products,
        "alerts": alerts,
        "analysis": analysis,
        "pending_days": sum(1 for point in analysis if point.get("threshold") is None),
        "sensitivity": sensitivity,
        "detectors": detectors.describe(),
        "detector_errors": detectors.errors,
        "available_period": {
            "start_date": ordered[0]["date"] if ordered else None,
            "end_date": ordered[-1]["date"] if ordered else None,
        },
        "selected_period": {
            "start_date": selected[0]["date"] if selected else start_date,
            "end_date": selected[-1]["date"] if selected else end_date,
        },
    }


def _with_day_kinds(rows: list[dict[str, Any]], days: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    return [{**row, "day_kind": days[row["date"]]["kind"], "day_kind_source": days[row["date"]]["source"]}
            for row in rows]


def detect_workspace_alerts(rows: list[dict[str, Any]], period_wide: bool = False) -> list[dict[str, Any]]:
    """Run the configured detectors on already-sorted workspace rows."""
    days = classify_days(rows)
    ctx = DetectionContext(rows=rows, scope="workspace", period_wide=period_wide,
                           day_kinds={d: v["kind"] for d, v in days.items()})
    return default_detectors().run(ctx)
