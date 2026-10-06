"""Follow the usual level of a daily series day by day, and notice when the level itself moves.

Judging each day on its own misses two things. Misuse that stays under the daily line but goes on
for days never crosses it, and a level that has genuinely moved (more people, a new habit) keeps
crossing it until the rolling baseline catches up. Both are the same event seen from two sides:
*the series has been above its usual level for several days running*.

That is what a one-sided CUSUM measures. Every day's score (how many spreads above the usual
level, on the ratio scale) is added to a running sum after subtracting a slack, so ordinary ups
and downs cancel out and only a persistent excess accumulates. When the sum passes the limit the
run of days that built it up is reported once, as a level shift starting on the run's first day,
and the baseline is re-anchored there: later days are compared with the new level instead of the
old one.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from statistics import median
from typing import Any, Callable

from app.detectors.stats import count_baseline, ratio_baseline, ratio_score, ratio_threshold


@dataclass(frozen=True)
class RatioScale:
    """Token amounts: compared by ratio, see ``stats.ratio_baseline``."""

    min_spread: float

    def baseline(self, values: list[float], scale: float) -> tuple[float, float]:
        return ratio_baseline(values, scale, self.min_spread)

    def score(self, value: float, center: float, spread: float, scale: float) -> float:
        return ratio_score(value, center, spread, scale)

    def line(self, center: float, spread: float, scale: float, factor: float) -> float:
        return ratio_threshold(center, spread, scale, factor)


@dataclass(frozen=True)
class CountScale:
    """Head counts: compared by difference, in people."""

    min_spread: float

    def baseline(self, values: list[float], scale: float) -> tuple[float, float]:
        return count_baseline(values, self.min_spread)

    def score(self, value: float, center: float, spread: float, scale: float) -> float:
        return (value - center) / spread

    def line(self, center: float, spread: float, scale: float, factor: float) -> float:
        return center + factor * spread


@dataclass
class LevelShift:
    start: str        # first day of the run that moved the level
    confirmed: str    # the day the accumulated evidence passed the limit
    kind: str         # workday / holiday: the days that were compared
    before: float     # usual value before the run
    after: float      # usual value during the run (median)
    days: int         # same-kind days in the run
    score: float      # mean daily score of the run


@dataclass
class Point:
    date: str
    kind: str
    value: float
    baseline: float | None = None
    spread: float | None = None
    scale: float | None = None
    score: float | None = None
    history: int = 0
    line: Callable[[float], float] | None = None  # the raw value that would score a given factor


def follow(
    rows: list[dict[str, Any]],
    value_of: Callable[[dict[str, Any]], float],
    kind_of: Callable[[str], str],
    measure: RatioScale | CountScale,
    *,
    window_days: int,
    min_history: int,
    scale_of: Callable[[int, list[dict[str, Any]]], float] | None = None,
    same_kind_only: bool = True,
    period_wide: bool = False,
    excluded: Callable[[Point], bool] | None = None,
    shift_slack: float = 1.0,
    shift_limit: float = 0.0,
    shift_cap: float = 3.0,
) -> tuple[list[Point], list[LevelShift]]:
    """Score every row against its baseline and collect the level shifts found on the way.

    ``rows`` are sorted by date and all carry the value. ``measure`` decides how days are compared
    (by ratio or by difference); ``scale_of(index, history)`` gives the workspace scale a ratio
    comparison needs. ``excluded(point)`` says whether a scored day must be left out of later
    baselines. ``shift_limit`` 0 turns level tracking off, and it is off in period-wide mode,
    where every day is compared with the whole selected period.
    """
    points: list[Point] = []
    shifts: list[LevelShift] = []
    left_out: set[str] = set()
    segment_start: dict[str, str] = {}          # kind -> first day of the current level
    sums: dict[str, float] = {}                 # kind -> CUSUM
    runs: dict[str, list[int]] = {}             # kind -> indexes of the days that built the sum
    track = shift_limit > 0 and not period_wide
    for index, row in enumerate(rows):
        day = row["date"]
        kind = kind_of(day) if same_kind_only else "all"
        point = Point(date=day, kind=kind_of(day), value=value_of(row))
        if period_wide:
            history = [other for other in rows if not same_kind_only or kind_of(other["date"]) == kind]
            enough = bool(history)
        else:
            cutoff = (date.fromisoformat(day) - timedelta(days=window_days)).isoformat()
            start = max(cutoff, segment_start.get(kind, cutoff))
            history = [other for other in rows[:index]
                       if other["date"] >= start and other["date"] not in left_out
                       and (not same_kind_only or kind_of(other["date"]) == kind)]
            # After a shift the days of the new level are all there is to compare with, however few.
            enough = len(history) >= (1 if kind in segment_start else min_history)
        point.history = len(history)
        if enough:
            if scale_of is not None:
                window = rows if period_wide else [other for other in rows[:index] if other["date"] >= cutoff]
                point.scale = max(scale_of(index, window), 1.0)
            point.baseline, point.spread = measure.baseline([value_of(other) for other in history], point.scale or 0.0)
            point.score = measure.score(point.value, point.baseline, point.spread, point.scale or 0.0)
            point.line = lambda factor, p=point: measure.line(p.baseline, p.spread, p.scale or 0.0, factor)
        points.append(point)
        if point.score is None:
            continue
        if excluded is not None and excluded(point):
            left_out.add(day)
        if not track:
            continue
        total = max(0.0, sums.get(kind, 0.0) + min(point.score, shift_cap) - shift_slack)
        if total == 0.0:
            sums[kind], runs[kind] = 0.0, []
            continue
        sums[kind] = total
        runs.setdefault(kind, []).append(index)
        if total < shift_limit:
            continue
        run = [points[i] for i in runs[kind]]
        # The sum can start creeping up on an ordinary, slightly high day; the level moved on the
        # first day that was at least one spread above the old level.
        while len(run) > 1 and (run[0].score or 0.0) < 1.0:
            run.pop(0)
        shifts.append(LevelShift(
            start=run[0].date, confirmed=day, kind=point.kind, before=run[0].baseline or 0.0,
            after=float(median(p.value for p in run)), days=len(run),
            score=sum(p.score or 0.0 for p in run) / len(run),
        ))
        segment_start[kind] = run[0].date
        left_out.difference_update(p.date for p in run)  # the run is the new normal, spikes included
        sums[kind], runs[kind] = 0.0, []
    return points, shifts
