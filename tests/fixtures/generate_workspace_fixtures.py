"""Generate the synthetic workspace fixtures used by the regression tests.

The data is invented with a fixed seed; it only mimics the *shape* of a real
September export: ~10 weekday users and ~3 weekend users, three quiet
weekdays (9/21-9/23) that the day-kind inference should treat as holidays
while their token usage stays at workday level, and one day (10/01) where
three Codex users burn far more than usual. Run it to regenerate:

    python tests/fixtures/generate_workspace_fixtures.py
"""
from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).parent
START, END = date(2026, 9, 3), date(2026, 10, 1)
HOLIDAY_WEEKDAYS = {date(2026, 9, 21), date(2026, 9, 22), date(2026, 9, 23)}  # inferred-holiday case


def day_kind(day: date) -> str:
    return "holiday" if day.weekday() >= 5 or day in HOLIDAY_WEEKDAYS else "workday"


def build(rng: random.Random) -> tuple[list[dict], list[dict]]:
    users, tokens = [], []
    day = START
    while day <= END:
        kind = day_kind(day)
        if kind == "workday":
            dau = {"Chat": rng.randint(9, 12), "Codex": rng.randint(6, 9), "Work": rng.randint(1, 3)}
            tok = {"Chat": rng.randint(30, 90) * 10**6, "Codex": rng.randint(40, 110) * 10**6, "Work": rng.randint(3, 80) * 10**5}
        else:
            dau = {"Chat": rng.randint(2, 4), "Codex": rng.randint(1, 3), "Work": rng.randint(0, 1)}
            tok = {"Chat": rng.randint(5, 40) * 10**6, "Codex": rng.randint(1, 30) * 10**6, "Work": 0 if dau["Work"] == 0 else rng.randint(2, 30) * 10**5}
        if day in HOLIDAY_WEEKDAYS:  # people kept working through the holidays: weekend-level DAU, workday-level tokens
            dau = {"Chat": 5, "Codex": rng.randint(1, 2), "Work": rng.randint(1, 2)}
            tok = {"Chat": rng.randint(100, 125) * 10**6, "Codex": rng.randint(5, 15) * 10**5, "Work": rng.randint(4, 25) * 10**5}
        if day == END:  # few users, huge Codex volume: the per-user detector must catch this
            dau = {"Chat": 10, "Codex": 3, "Work": 1}
            tok = {"Chat": 14 * 10**6, "Codex": 205 * 10**6, "Work": 7 * 10**6}
        nxt = day + timedelta(days=1)
        users.append({"Start Time": f"{day}T00:00:00Z", "End Time": f"{nxt}T00:00:00Z", **dau})
        tokens.append({"Start Time": str(day), "End Time": str(nxt), **tok})
        day = nxt
    return users, tokens


def document(chart_key: str, title: str, label: str, rows: list[dict], source: str) -> dict:
    totals = {column: sum(row[column] for row in rows) for column in ("Chat", "Codex", "Work")}
    return {
        "chart_key": chart_key,
        "chart_title": title,
        "summary": {"is_partial": True, "label": label, "previous_value": 0, "value": sum(totals.values())},
        "series": [
            {"column": column, "key": key, "label": column, "source": source,
             "summary": {"is_partial": True, "label": column, "previous_value": 0, "value": totals[column]}}
            for column, key in (("Chat", "chatgpt"), ("Codex", "codex"), ("Work", "work"))
        ],
        "rows": rows,
    }


def main() -> None:
    users, tokens = build(random.Random(20260903))
    (HERE / "workspace-active-users-2026-09.json").write_text(
        json.dumps(document("active-users", "Active users", "Active users", users, "shared"), ensure_ascii=False, indent=2) + "\n")
    (HERE / "workspace-tokens-2026-09.json").write_text(
        json.dumps(document("tokens", "Tokens", "Tokens", tokens, "credits_reporting"), ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
