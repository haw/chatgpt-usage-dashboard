from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from app.detectors import DetectionContext, DetectorSet, build_detector_set


def build_dashboard(rows: list[dict[str, Any]], state: dict[str, Any]) -> dict[str, Any]:
    daily: dict[str, float] = defaultdict(float)
    users: dict[str, dict[str, Any]] = {}
    products: dict[str, float] = defaultdict(float)
    user_daily: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for row in rows:
        activity = float(row.get("activity", 0))
        daily[row["date"]] += activity
        products[row["product"]] += activity
        user_id = row["user_id"]
        user = users.setdefault(user_id, {"id": user_id, "name": row.get("user_name", user_id), "activity": 0.0})
        user["activity"] += activity
        user_daily[user_id][row["date"]] += activity

    alerts = detect_alerts(user_daily, users)
    daily_rows = [{"date": date, "activity": round(value, 2)} for date, value in sorted(daily.items())]
    user_rows = sorted(
        ({**value, "activity": round(value["activity"], 2), "daily": dict(sorted(user_daily[key].items()))}
         for key, value in users.items()),
        key=lambda item: item["activity"], reverse=True,
    )
    product_rows = [
        {"product": product, "activity": round(value, 2)}
        for product, value in sorted(products.items(), key=lambda item: item[1], reverse=True)
    ]
    total = sum(daily.values())
    return {
        "state": state,
        "kpis": {
            "active_users": len([u for u in user_rows if u["activity"] > 0]),
            "total_activity": round(total, 2),
            "daily_average": round(total / len(daily_rows), 2) if daily_rows else 0,
            "alerts": len(alerts),
        },
        "daily": daily_rows,
        "users": user_rows,
        "products": product_rows,
        "alerts": alerts,
    }


def detect_alerts(user_daily: dict[str, dict[str, float]], users: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    samples = [value for values in user_daily.values() for value in values.values() if value > 0]
    threshold = _percentile(samples, 0.95) if len(samples) >= 4 else math.inf
    alerts: list[dict[str, Any]] = []
    for user_id, values in user_daily.items():
        ordered = sorted(values.items())
        for index, (date, value) in enumerate(ordered):
            previous = [v for _, v in ordered[:index] if v > 0]
            baseline = sum(previous) / len(previous) if previous else 0
            if value >= 10 and baseline > 0 and value >= baseline * 2:
                alerts.append(_alert("spike", user_id, users, date, value, f"直前平均の{value / baseline:.1f}倍"))
            elif value > 0 and value >= threshold:
                alerts.append(_alert("high_volume", user_id, users, date, value, "期間内の上位5%"))
        if len(ordered) >= 3 and all(value == 0 for _, value in ordered[-3:]):
            date, _ = ordered[-1]
            alerts.append(_alert("inactive", user_id, users, date, 0, "直近3日間の利用なし"))
    return sorted(alerts, key=lambda item: (item["date"], item["activity"]), reverse=True)


def _alert(kind: str, user_id: str, users: dict[str, dict[str, Any]], date: str, value: float, reason: str) -> dict[str, Any]:
    return {"type": kind, "user_id": user_id, "user_name": users[user_id]["name"], "date": date,
            "activity": round(value, 2), "reason": reason}


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return math.inf
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * percentile) - 1)
    return ordered[index]


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
    ctx = DetectionContext(rows=daily, scope="individual")
    analysis = detectors.series(ctx)
    alerts = detectors.run(ctx)
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
) -> dict[str, Any]:
    detectors = detectors or default_detectors()
    ordered = sorted(rows, key=lambda row: row["date"])
    selected = [
        row for row in ordered
        if (start_date is None or row["date"] >= start_date)
        and (end_date is None or row["date"] <= end_date)
    ]
    period_wide = start_date is not None or end_date is not None
    ctx = DetectionContext(rows=selected, scope="workspace", period_wide=period_wide)
    alerts = detectors.run(ctx)
    analysis = detectors.series(ctx)
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


def detect_workspace_alerts(rows: list[dict[str, Any]], period_wide: bool = False) -> list[dict[str, Any]]:
    """Run the configured detectors on already-sorted workspace rows."""
    return default_detectors().run(DetectionContext(rows=rows, scope="workspace", period_wide=period_wide))
