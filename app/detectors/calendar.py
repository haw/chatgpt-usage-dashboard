"""Classify each day as a workday or a holiday.

Weekends are holidays by the calendar. Weekdays are inferred from the data:
a weekday whose activity is far below the typical weekday level is treated
as a holiday (public holidays, company closures). Viewer overrides win over
both. No holiday calendar is bundled, so the rules keep working for any
country and any company-specific closure.
"""
from __future__ import annotations

from datetime import date
from statistics import median
from typing import Any

WORKDAY = "workday"
HOLIDAY = "holiday"
KINDS = (WORKDAY, HOLIDAY)

# A weekday counts as a holiday when its DAU is at or below this share of the
# typical weekday DAU; tokens are the fallback when DAU is missing.
DAU_HOLIDAY_RATIO = 0.5
TOKEN_HOLIDAY_RATIO = 0.35
MIN_REFERENCE_SAMPLES = 3


def _activity(row: dict[str, Any], group: str) -> float | None:
    values = row.get(group)
    if values is None:
        return None
    if group == "tokens":
        return float(values.get("total", 0))
    return float(max(values.values())) if values else None


def classify_days(
    rows: list[dict[str, Any]],
    overrides: dict[str, str] | None = None,
    infer: bool = True,
) -> dict[str, dict[str, str]]:
    """Return ``{date: {"kind": ..., "source": ...}}`` for every row.

    ``source`` explains the decision: ``weekend``, ``weekday``, ``inferred``
    (weekday with holiday-level activity) or ``override``.
    """
    overrides = {day: kind for day, kind in (overrides or {}).items() if kind in KINDS}
    calendar_weekday = {row["date"]: date.fromisoformat(row["date"]).weekday() < 5 for row in rows}
    references: dict[str, float | None] = {}
    if infer:
        for group in ("active_users", "tokens"):
            samples = [
                value for row in rows
                if calendar_weekday[row["date"]] and (value := _activity(row, group)) is not None
            ]
            references[group] = float(median(samples)) if len(samples) >= MIN_REFERENCE_SAMPLES else None
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        day = row["date"]
        if day in overrides:
            result[day] = {"kind": overrides[day], "source": "override"}
            continue
        if not calendar_weekday[day]:
            result[day] = {"kind": HOLIDAY, "source": "weekend"}
            continue
        kind, source = WORKDAY, "weekday"
        if infer:
            for group, ratio in (("active_users", DAU_HOLIDAY_RATIO), ("tokens", TOKEN_HOLIDAY_RATIO)):
                value = _activity(row, group)
                reference = references.get(group)
                if value is None or reference is None:
                    continue
                if value <= reference * ratio:
                    kind, source = HOLIDAY, "inferred"
                break  # the first available metric decides; tokens are only a fallback
        result[day] = {"kind": kind, "source": source}
    return result


def parse_override_list(holidays: str | None, workdays: str | None) -> dict[str, str]:
    """Build the override map from the comma-separated query values."""
    overrides: dict[str, str] = {}
    for raw, kind in ((holidays, HOLIDAY), (workdays, WORKDAY)):
        for item in (raw or "").split(","):
            item = item.strip()
            if not item:
                continue
            try:
                overrides[date.fromisoformat(item).isoformat()] = kind
            except ValueError as exc:
                raise ValueError(f"日付の形式が不正です: {item}") from exc
    return overrides
