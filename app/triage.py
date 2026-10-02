"""Build the "今日の確認" (triage) view: a short ranked list of days worth looking at.

Ranking is independent of the viewer's sensitivity (it always runs detectors at
1.0) so the top of the list is stable. A day's rank comes from how many
independent detectors reacted, whether the pattern is new, and the strongest
severity; days the analyst already checked drop to the reference tier.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.detectors import DetectionContext, DetectorSet
from app.detectors.calendar import classify_days

TOP_K = 5
NOVELTY_DAYS = 14   # a (detector, product) seen in this many prior days is "continuing", not new
TIER_TODAY, TIER_WEEK, TIER_REFERENCE = "today", "week", "reference"
DISPOSITION_KINDS = ("checked", "cleared")  # a single "seen" mark that can be undone


def build_triage(
    rows: list[dict[str, Any]],
    state: dict[str, Any],
    detectors: DetectorSet,
    dispositions: list[dict[str, Any]],
    day_overrides: dict[str, str] | None = None,
    today: str | None = None,
    top_k: int = TOP_K,
) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: row["date"])
    days = classify_days(ordered, day_overrides)
    ctx = DetectionContext(rows=ordered, scope="workspace",
                           day_kinds={d: v["kind"] for d, v in days.items()}, today=today)
    signals = detectors.run(ctx)
    analysis = detectors.series(ctx)
    operations = [s for s in signals if s["detector"] in _operations_ids(detectors)]
    observations = [s for s in signals if s["detector"] not in _operations_ids(detectors)]
    latest_disposition = {d["date"]: d for d in sorted(dispositions, key=lambda d: d["recorded_at"])}
    latest_disposition = {day: d for day, d in latest_disposition.items() if d["kind"] == "checked"}
    checked_total = len(latest_disposition)

    by_date: dict[str, list[dict[str, Any]]] = {}
    for signal in observations:
        by_date.setdefault(signal["date"], []).append(signal)
    history = _first_seen_index(observations)
    entries = []
    for day, items in by_date.items():
        entry = _entry(day, items, days.get(day, {}), ordered, history, latest_disposition.get(day))
        entries.append(entry)
    entries.sort(key=lambda e: (-e["score"], e["date"]), reverse=False)
    entries.sort(key=lambda e: e["score"], reverse=True)
    for index, entry in enumerate(entries):
        if entry["disposition"] and entry["disposition"]["kind"] == "checked":
            entry["tier"] = TIER_REFERENCE
        elif entry["detectors"] == 0:
            entry["tier"] = TIER_REFERENCE
        elif index < top_k and (entry["detectors"] >= 2 or entry["max_severity"] == "high" or entry["novel"]):
            entry["tier"] = TIER_TODAY
        else:
            entry["tier"] = TIER_WEEK
    tier_order = {TIER_TODAY: 0, TIER_WEEK: 1, TIER_REFERENCE: 2}
    entries.sort(key=lambda e: (tier_order[e["tier"]], -e["score"], e["date"]))
    entries.sort(key=lambda e: (tier_order[e["tier"]], -e["score"]))
    # within a tier, newer dates first for equal scores
    entries = sorted(entries, key=lambda e: (tier_order[e["tier"]], -e["score"], _neg_date(e["date"])))

    latest = ordered[-1]["date"] if ordered else None
    reference_day = today or date.today().isoformat()
    age = (date.fromisoformat(reference_day) - date.fromisoformat(latest)).days if latest else None
    return {
        "status": {
            "latest_date": latest,
            "as_of": reference_day,
            "age_days": age,
            "stale": bool(operations),
            "stale_reason": operations[0]["reason"] if operations else None,
            "completed_at": state.get("completed_at"),
            "stored_days": len(ordered),
            "pending_days": sum(1 for point in analysis if point.get("threshold") is None),
            "baseline": "同じ区分（平日/休日）の直前28日",
            "checked_days": checked_total,
        },
        "today": [e for e in entries if e["tier"] == TIER_TODAY],
        "week": [e for e in entries if e["tier"] == TIER_WEEK],
        "reference": [e for e in entries if e["tier"] == TIER_REFERENCE],
        "detector_errors": detectors.errors,
    }


def checked_dates(dispositions: list[dict[str, Any]]) -> list[str]:
    """Dates whose latest record is "checked"."""
    latest = {d["date"]: d for d in sorted(dispositions, key=lambda d: d["recorded_at"])}
    return sorted(day for day, d in latest.items() if d["kind"] == "checked")


def _neg_date(day: str) -> int:
    return -int(day.replace("-", ""))


def _operations_ids(detectors: DetectorSet) -> set[str]:
    return {d.id for d in detectors.detectors if d.group == "operations"}


def _first_seen_index(signals: list[dict[str, Any]]) -> dict[tuple[str, str | None], list[str]]:
    """Dates on which each (detector, product) produced a non-info signal, sorted."""
    index: dict[tuple[str, str | None], list[str]] = {}
    for signal in signals:
        if signal["severity"] == "info":
            continue
        index.setdefault((signal["detector"], signal["product"]), []).append(signal["date"])
    for dates in index.values():
        dates.sort()
    return index


def _entry(
    day: str,
    items: list[dict[str, Any]],
    kind_info: dict[str, str],
    rows: list[dict[str, Any]],
    history: dict[tuple[str, str | None], list[str]],
    disposition: dict[str, Any] | None,
) -> dict[str, Any]:
    strong = [s for s in items if s["severity"] != "info"]
    current = date.fromisoformat(day)
    novelty_floor = (current - timedelta(days=NOVELTY_DAYS)).isoformat()
    observations = []
    novel_any = False
    for signal in sorted(items, key=lambda s: {"high": 0, "medium": 1, "info": 2}[s["severity"]]):
        seen = history.get((signal["detector"], signal["product"]), [])
        earlier = [d for d in seen if novelty_floor <= d < day]
        streak = _streak(seen, day)
        novel = signal["severity"] != "info" and not earlier
        novel_any = novel_any or novel
        observations.append({**signal, "novel": novel, "streak": streak})
    max_severity = "high" if any(s["severity"] == "high" for s in items) else (
        "medium" if strong else "info")
    # Alert on onset, not continuation: a detector that only continues yesterday's
    # pattern counts less than one that starts firing today.
    onset = {o["detector"] for o in observations if o["severity"] != "info" and o["streak"] == 1}
    continuing = {o["detector"] for o in observations if o["severity"] != "info"} - onset
    detectors = onset | continuing
    score = len(onset) * 10 + len(continuing) * 4 + (5 if max_severity == "high" else 0) + (3 if novel_any else 0)
    row = next((r for r in rows if r["date"] == day), {})
    facts = {
        "kind": kind_info.get("kind", "workday"),
        "kind_source": kind_info.get("source", "weekday"),
        "max_dau": max(row["active_users"].values()) if row.get("active_users") else None,
        "total_tokens": row["tokens"]["total"] if row.get("tokens") else None,
    }
    return {
        "date": day, "score": score, "detectors": len(detectors), "max_severity": max_severity,
        "novel": novel_any, "continuing": bool(continuing) and not onset,
        "streak": max((o["streak"] for o in observations if o["severity"] != "info"), default=0),
        "facts": facts, "observations": observations,
        "disposition": disposition, "tier": None,
    }


def _streak(seen: list[str], day: str) -> int:
    """How many consecutive days up to ``day`` (inclusive) this pattern fired."""
    if day not in seen:
        return 0
    streak = 1
    cursor = date.fromisoformat(day)
    seen_set = set(seen)
    while (cursor - timedelta(days=1)).isoformat() in seen_set:
        cursor -= timedelta(days=1)
        streak += 1
    return streak
