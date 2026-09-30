from __future__ import annotations

import math
from collections import defaultdict
from typing import Any


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

