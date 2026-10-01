from __future__ import annotations

import math
from collections import defaultdict
from statistics import median
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


PRODUCTS = ("chat", "codex", "work")


def build_individual_dashboard(
    rows: list[dict[str, Any]],
    state: dict[str, Any],
    user_id: str | None = None,
) -> dict[str, Any]:
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
    analysis = build_token_analysis(daily)
    total = sum(row["tokens"]["total"] for row in daily)
    product_totals = {product: sum(row["tokens"][product] for row in daily) for product in PRODUCTS}
    return {
        "state": state,
        "users": users,
        "selected_user": users_by_id.get(selected_id),
        "daily": daily,
        "analysis": analysis,
        "product_totals": product_totals,
        "kpis": {
            "total_tokens": total,
            "daily_average_tokens": round(total / len(daily)) if daily else 0,
            "latest_tokens": daily[-1]["tokens"]["total"] if daily else 0,
            "alerts": sum(1 for point in analysis if point["is_anomaly"]),
        },
    }


def build_workspace_dashboard(
    rows: list[dict[str, Any]],
    state: dict[str, Any],
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: row["date"])
    selected = [
        row for row in ordered
        if (start_date is None or row["date"] >= start_date)
        and (end_date is None or row["date"] <= end_date)
    ]
    period_wide = start_date is not None or end_date is not None
    alerts = detect_workspace_alerts(selected, period_wide=period_wide)
    analysis = build_token_analysis(selected, period_wide=period_wide)
    total_tokens = sum(row["tokens"]["total"] for row in selected)
    latest = selected[-1] if selected else None
    products = []
    for product in PRODUCTS:
        products.append({
            "product": product,
            "tokens": sum(row["tokens"][product] for row in selected),
            "average_active_users": round(
                sum(row["active_users"][product] for row in selected) / len(selected), 1
            ) if selected else 0,
        })
    return {
        "state": state,
        "kpis": {
            "latest_max_product_dau": max(latest["active_users"].values()) if latest else 0,
            "total_tokens": total_tokens,
            "daily_average_tokens": round(total_tokens / len(selected)) if selected else 0,
            "alerts": len(alerts),
        },
        "daily": selected,
        "products": products,
        "alerts": alerts,
        "analysis": analysis,
        "available_period": {
            "start_date": ordered[0]["date"] if ordered else None,
            "end_date": ordered[-1]["date"] if ordered else None,
        },
        "selected_period": {
            "start_date": selected[0]["date"] if selected else start_date,
            "end_date": selected[-1]["date"] if selected else end_date,
        },
    }


def build_token_analysis(
    rows: list[dict[str, Any]],
    start_date: str | None = None,
    end_date: str | None = None,
    period_wide: bool = False,
) -> list[dict[str, Any]]:
    """Build total-token observations with the same rolling threshold used by alerts."""
    result: list[dict[str, Any]] = []
    period_center: float | None = None
    period_threshold: float | None = None
    if period_wide and rows:
        period_values = [row["tokens"]["total"] for row in rows]
        period_center = float(median(period_values))
        period_mad = float(median(abs(sample - period_center) for sample in period_values))
        period_threshold = period_center + (3.5 * period_mad / 0.6745) if period_mad else max(period_center * 2, 1)
    for index, row in enumerate(rows):
        if start_date and row["date"] < start_date:
            continue
        if end_date and row["date"] > end_date:
            continue
        history = rows[max(0, index - 7):index]
        center: float | None = None
        threshold: float | None = None
        if period_wide:
            center = period_center
            threshold = period_threshold
        elif len(history) >= 5:
            values = [previous["tokens"]["total"] for previous in history]
            center = float(median(values))
            mad = float(median(abs(sample - center) for sample in values))
            threshold = center + (3.5 * mad / 0.6745) if mad else max(center * 2, 1)
        value = row["tokens"]["total"]
        result.append({
            "date": row["date"],
            "value": value,
            "baseline": round(center, 1) if center is not None else None,
            "threshold": round(threshold, 1) if threshold is not None else None,
            "is_anomaly": threshold is not None and value >= threshold,
        })
    return result


def detect_workspace_alerts(rows: list[dict[str, Any]], period_wide: bool = False) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    metrics = [("tokens", "total"), *(('tokens', p) for p in PRODUCTS), *(('active_users', p) for p in PRODUCTS)]
    for group, product in metrics:
        for index, row in enumerate(rows):
            history = rows if period_wide else rows[max(0, index - 7):index]
            if (not period_wide and len(history) < 5) or not history:
                continue
            values = [previous[group][product] for previous in history]
            value = row[group][product]
            center = float(median(values))
            mad = float(median(abs(sample - center) for sample in values))
            score = 0.6745 * (value - center) / mad if mad else None
            if group == "tokens":
                anomalous = value > center and ((score is not None and score >= 3.5) or (mad == 0 and value >= max(center * 2, 1)))
                kind = "token_spike"
            else:
                ratio_outlier = mad == 0 and ((center == 0 and value >= 2) or (center > 0 and (value >= center * 2 or value <= center * .5)))
                anomalous = abs(value - center) >= 2 and ((score is not None and abs(score) >= 3.5) or ratio_outlier)
                kind = "dau_spike" if value > center else "dau_drop"
            if anomalous:
                metric_label = "総トークン" if product == "total" else ("トークン" if group == "tokens" else "DAU")
                alerts.append({
                    "type": kind,
                    "metric": metric_label,
                    "product": None if product == "total" else product,
                    "date": row["date"],
                    "value": value,
                    "baseline": round(center, 1),
                    "score": round(score, 2) if score is not None else None,
                    "reason": (f"選択期間の中央値 {center:,.1f} から大きく変化" if period_wide else f"直前{len(history)}日の中央値 {center:,.1f} から大きく変化"),
                })
    return sorted(alerts, key=lambda item: (item["date"], item["metric"]), reverse=True)
