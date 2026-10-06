"""Shared statistics for detectors: robust baselines and history windows."""
from __future__ import annotations

import math
from datetime import date, timedelta
from statistics import median
from typing import Any

MAD_SCALE = 0.6745  # converts MAD to a standard-deviation equivalent for normal data


def ratio_baseline(values: list[float], scale: float, min_spread: float) -> tuple[float, float]:
    """Baseline for quantities that vary by ratio (token counts): (typical value, spread).

    Token usage changes multiplicatively: a day is "three times the usual", not "200M more than
    usual", and usual days themselves differ by tens of percent. So the comparison is made on
    ln(value + scale): the centre is the median and the spread is the MAD turned into a
    standard-deviation equivalent, never below ``min_spread`` (a few similar days must not make
    the next ordinary day look extreme).

    ``scale`` is an amount of tokens that is ordinary for this workspace (a typical workday).
    Adding it to both sides keeps ratios between small amounts in proportion: going from 0.1M to
    2M is "20 times" on paper but nothing next to a 100M day, while 0 to 150M still stands out.
    """
    logs = [math.log(value + scale) for value in values]
    center = float(median(logs))
    spread = max(float(median(abs(sample - center) for sample in logs)) / MAD_SCALE, min_spread)
    return math.exp(center) - scale, spread


def ratio_score(value: float, typical: float, spread: float, scale: float) -> float:
    """How many spreads ``value`` lies above (or below) the typical value, on the ratio scale."""
    return (math.log(value + scale) - math.log(typical + scale)) / spread


def ratio_threshold(typical: float, spread: float, scale: float, factor: float) -> float:
    """The raw value whose ratio score equals ``factor``."""
    return math.exp(math.log(typical + scale) + factor * spread) - scale


def count_baseline(values: list[float], min_spread: float) -> tuple[float, float]:
    """Baseline for head counts (DAU): (median, spread in people, at least ``min_spread``)."""
    center = float(median(values))
    spread = max(float(median(abs(sample - center) for sample in values)) / MAD_SCALE, min_spread)
    return center, spread


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
