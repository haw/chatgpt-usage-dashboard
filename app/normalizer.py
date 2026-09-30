from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


IDENTITY_KEYS = ("user_id", "user_email", "email", "user_name", "username")
PRODUCT_KEYS = ("product", "product_name", "surface", "client", "source")
DATE_KEYS = ("date", "start_date", "day")
IGNORED_NUMERIC_KEYS = {
    "start_time", "end_time", "created_at", "updated_at", "timestamp", "unix_time"
}


def normalize_pages(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in pages:
        items = page.get("data") or page.get("results") or page.get("usage") or []
        if isinstance(items, dict):
            items = items.get("data") or items.get("results") or [items]
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            rows.extend(_normalize_item(item))
    return _coalesce(rows)


def _normalize_item(item: dict[str, Any]) -> list[dict[str, Any]]:
    date = _extract_date(item)
    nested = item.get("results") or item.get("records") or item.get("rows")
    if isinstance(nested, list):
        result = []
        for child in nested:
            if isinstance(child, dict):
                result.append(_make_row(child, date or _extract_date(child)))
        return result
    return [_make_row(item, date)]


def _make_row(item: dict[str, Any], date: str | None) -> dict[str, Any]:
    user_id = _first(item, IDENTITY_KEYS) or _nested_user(item) or "workspace"
    user_name = _first(item, ("user_name", "name", "email", "user_email")) or str(user_id)
    product = _first(item, PRODUCT_KEYS) or "chatgpt"
    metrics = _numeric_leaves(item)
    activity = sum(value for key, value in metrics.items() if key not in IGNORED_NUMERIC_KEYS)
    return {
        "date": date or datetime.now(timezone.utc).date().isoformat(),
        "user_id": str(user_id),
        "user_name": str(user_name),
        "product": str(product),
        "activity": round(activity, 4),
        "metrics": metrics,
    }


def _extract_date(item: dict[str, Any]) -> str | None:
    value = _first(item, DATE_KEYS)
    if value:
        return str(value)[:10]
    timestamp = item.get("start_time")
    if isinstance(timestamp, (int, float)):
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).date().isoformat()
    return None


def _first(item: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return None


def _nested_user(item: dict[str, Any]) -> Any:
    user = item.get("user")
    if isinstance(user, dict):
        return _first(user, ("id", "email", "name"))
    return None


def _numeric_leaves(item: dict[str, Any], prefix: str = "") -> dict[str, float]:
    metrics: dict[str, float] = {}
    for key, value in item.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            metrics[path] = float(value)
        elif isinstance(value, dict):
            metrics.update(_numeric_leaves(value, path))
    return metrics


def _coalesce(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    combined: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row["date"], row["user_id"], row["product"])
        if key not in combined:
            combined[key] = row
            continue
        target = combined[key]
        target["activity"] = round(target["activity"] + row["activity"], 4)
        for metric, value in row["metrics"].items():
            target["metrics"][metric] = target["metrics"].get(metric, 0) + value
    return list(combined.values())

