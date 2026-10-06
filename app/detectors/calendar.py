"""Classify each day as a workday or a holiday.

Weekends are holidays by the calendar. Weekdays are inferred from the data:
a weekday whose activity is far below the weekdays around it is treated
as a holiday (public holidays, company closures). Viewer overrides win over
both. No holiday calendar is bundled, so the rules keep working for any
country and any company-specific closure.

"Around it" matters: a workspace that grows from 5 to 10 daily users would otherwise have its
early, perfectly normal weekdays classified as holidays (and real holidays later on missed).
A holiday is a dip: the day must be low against the weekdays before it and against the weekdays
after it, so the last days before usage steps up (or the first after it steps down) stay workdays.
"""
from __future__ import annotations

from datetime import date, timedelta
from statistics import median
from typing import Any

WORKDAY = "workday"
HOLIDAY = "holiday"
KINDS = (WORKDAY, HOLIDAY)

# A weekday counts as a holiday when its DAU is at or below this share of the
# typical DAU of the surrounding weekdays; tokens are the fallback when DAU is missing.
DAU_HOLIDAY_RATIO = 0.55
TOKEN_HOLIDAY_RATIO = 0.35
MIN_REFERENCE_SAMPLES = 3
NEIGHBOUR_DAYS = 14  # weekdays within this many calendar days, before and after, are the reference


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
    weekdays = {
        group: [(row["date"], value) for row in rows
                if calendar_weekday[row["date"]] and (value := _activity(row, group)) is not None]
        for group in ("active_users", "tokens")
    } if infer else {}

    def reference(group: str, day: str, holidays: set[str]) -> float | None:
        """Typical weekday activity around ``day``, leaving out weekdays already known to be holidays."""
        current = date.fromisoformat(day)
        low = (current - timedelta(days=NEIGHBOUR_DAYS)).isoformat()
        high = (current + timedelta(days=NEIGHBOUR_DAYS)).isoformat()
        samples = [(other, value) for other, value in weekdays.get(group, []) if other not in holidays]
        before = [value for other, value in samples if low <= other < day]
        after = [value for other, value in samples if day < other <= high]
        sides = [float(median(side)) for side in (before, after) if len(side) >= MIN_REFERENCE_SAMPLES]
        if sides:
            return min(sides)
        # too few days on either side (a short data set): use whatever surrounds the day
        return float(median(before + after)) if len(before + after) >= MIN_REFERENCE_SAMPLES else None

    def inferred_holidays(known: set[str]) -> set[str]:
        found = set()
        for row in rows:
            day = row["date"]
            if day in overrides or not calendar_weekday[day]:
                continue
            for group, ratio in (("active_users", DAU_HOLIDAY_RATIO), ("tokens", TOKEN_HOLIDAY_RATIO)):
                value = _activity(row, group)
                typical = reference(group, day, known - {day})
                if value is None or typical is None:
                    continue
                if value <= typical * ratio:
                    found.add(day)
                break  # the first available metric decides; tokens are only a fallback
        return found

    # A run of holidays (a long weekend) would drag its own reference down, so holidays found in one
    # pass are left out of the reference in the next until nothing changes.
    manual = {day for day, kind in overrides.items() if kind == HOLIDAY}
    inferred: set[str] = set()
    if infer:
        for _ in range(5):
            found = inferred_holidays(manual | inferred)
            if found == inferred:
                break
            inferred = found

    result: dict[str, dict[str, str]] = {}
    for row in rows:
        day = row["date"]
        if day in overrides:
            result[day] = {"kind": overrides[day], "source": "override"}
        elif not calendar_weekday[day]:
            result[day] = {"kind": HOLIDAY, "source": "weekend"}
        elif day in inferred:
            result[day] = {"kind": HOLIDAY, "source": "inferred"}
        else:
            result[day] = {"kind": WORKDAY, "source": "weekday"}
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
