"""Shared statistics for detectors: robust baselines and history windows."""
from __future__ import annotations

from datetime import date, timedelta
from statistics import median
from typing import Any

MAD_SCALE = 0.6745  # converts MAD to a standard-deviation equivalent for normal data


def robust_baseline(values: list[float], factor: float = 3.5) -> tuple[float, float, float]:
    """Return (median, MAD, upper threshold) for the given history values.

    When MAD is 0 (flat history) the threshold falls back to twice the median,
    with a floor of 1 so a flat zero history still flags any activity.
    """
    center = float(median(values))
    mad = float(median(abs(sample - center) for sample in values))
    threshold = center + (factor * mad / MAD_SCALE) if mad else max(center * 2, 1)
    return center, mad, threshold


def robust_score(value: float, center: float, mad: float) -> float | None:
    """Robust Z-score; None when MAD is 0 because the score is undefined."""
    return MAD_SCALE * (value - center) / mad if mad else None


def rolling_history(
    rows: list[dict[str, Any]],
    index: int,
    window_days: int,
    exclude: set[str] | None = None,
    same_kind_as: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Rows strictly before ``rows[index]`` within ``window_days`` calendar days.

    ``rows`` must be sorted by date. Dates in ``exclude`` (e.g. days already
    flagged as anomalous) are left out so they do not inflate the baseline.
    With ``same_kind_as`` (date -> kind) only days of the same kind as the
    current one are kept, so holidays are compared with holidays.
    """
    current = date.fromisoformat(rows[index]["date"])
    cutoff = (current - timedelta(days=window_days)).isoformat()
    kind = same_kind_as.get(rows[index]["date"], "workday") if same_kind_as is not None else None
    history = []
    for previous in reversed(rows[:index]):
        if previous["date"] < cutoff:
            break
        if exclude and previous["date"] in exclude:
            continue
        if kind is not None and same_kind_as.get(previous["date"], "workday") != kind:
            continue
        history.append(previous)
    history.reverse()
    return history


def period_history(
    rows: list[dict[str, Any]],
    index: int,
    same_kind_as: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Every row of the selected period with the same day kind (period-wide mode)."""
    if same_kind_as is None:
        return list(rows)
    kind = same_kind_as.get(rows[index]["date"], "workday")
    return [row for row in rows if same_kind_as.get(row["date"], "workday") == kind]
