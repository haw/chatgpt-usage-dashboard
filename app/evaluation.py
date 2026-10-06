"""Check the detection rules against a period that is known to be clean.

Two questions decide whether a rule set is usable:

1. How often does it cry wolf? Every day it flags in a period without abuse is a day the analyst
   looks at for nothing.
2. Would it notice abuse? Synthetic misuse is added to one day at a time (or to several workdays
   in a row, for misuse that stays small and goes on) and the rules are run again; the share of
   attempts in which the addition is flagged is the detection rate.

Both are reported for several sensitivities so the trade-off is visible. The amounts injected are
multiples of the workspace's own typical workday, so the result does not depend on its size.

    python -m app evaluate            # uses the stored workspace data and config/detectors.toml
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import median
from typing import Any

from app.detectors import DetectionContext, DetectorSet
from app.detectors.calendar import classify_days
from app.detectors.stats import rolling_history

SENSITIVITIES = (0.5, 1.0, 1.4, 2.0)
WINDOW_DAYS = 28
MIN_WORKDAYS = 5
LEAD_DAYS = 7  # how far before the injected misuse a newly flagged day still counts as noticing it


@dataclass(frozen=True)
class Scenario:
    """Misuse added to one day, or to ``days`` workdays in a row.

    ``tokens`` is the amount added per day, as a multiple of a typical workday's total.
    """

    key: str
    label: str
    tokens: float = 0.0
    users: int = 0
    product: str = "codex"
    holidays_only: bool = False
    days: int = 1


SCENARIOS = (
    Scenario("takeover_small", "既存アカウントの乗っ取り（平日1日分の半分を消費）", tokens=0.5),
    Scenario("takeover_medium", "既存アカウントの乗っ取り（平日1日分を消費）", tokens=1.0),
    Scenario("takeover_large", "既存アカウントの乗っ取り（平日3日分を消費）", tokens=3.0),
    Scenario("takeover_chat", "既存アカウントの乗っ取り（Chatで平日1日分を消費）", tokens=1.0, product="chat"),
    Scenario("new_account", "不正なアカウント1つが平日1日分を消費", tokens=1.0, users=1),
    Scenario("holiday_use", "休日に不正なアカウント1つが平日1日分の半分を消費", tokens=0.5, users=1, holidays_only=True),
    Scenario("accounts_only", "アカウントが3つ増える（利用量は増えない）", users=3, product="chat"),
)

# Misuse that stays under the daily line and goes on: the same amount on consecutive workdays.
SUSTAINED = (
    Scenario("slow_quarter_10", "毎日 平日1日分の1/4 を10平日", tokens=0.25, days=10),
    Scenario("slow_half_5", "毎日 平日1日分の半分 を5平日", tokens=0.5, days=5),
    Scenario("slow_half_10", "毎日 平日1日分の半分 を10平日", tokens=0.5, days=10),
    Scenario("slow_one_3", "毎日 平日1日分 を3平日", tokens=1.0, days=3),
    Scenario("slow_one_5", "毎日 平日1日分 を5平日", tokens=1.0, days=5),
)


def _flagged_days(rows: list[dict[str, Any]], detectors: DetectorSet, sensitivity: float, today: str | None,
                  overrides: dict[str, str] | None = None, level_shifts: bool = False) -> dict[str, list[dict[str, Any]]]:
    """Dates with at least one signal above the line (not "info"), with those signals."""
    days = classify_days(rows, overrides)
    ctx = DetectionContext(rows=rows, scope="workspace", day_kinds={d: v["kind"] for d, v in days.items()},
                           sensitivity=sensitivity, today=today, level_shifts=level_shifts)
    operations = {d.id for d in detectors.detectors if d.group == "operations"}
    result: dict[str, list[dict[str, Any]]] = {}
    for signal in detectors.run(ctx):
        if signal["severity"] != "info" and signal["detector"] not in operations:
            result.setdefault(signal["date"], []).append(signal)
    return result


def false_alarms(rows: list[dict[str, Any]], detectors: DetectorSet, sensitivities: tuple[float, ...] = SENSITIVITIES,
                 today: str | None = None, level_shifts: bool = False) -> list[dict[str, Any]]:
    """Per sensitivity: which days of the (clean) data are flagged, and by which detectors."""
    report = []
    for sensitivity in sensitivities:
        flagged = _flagged_days(rows, detectors, sensitivity, today, level_shifts=level_shifts)
        by_detector: dict[str, int] = {}
        for signals in flagged.values():
            for detector in {signal["detector"] for signal in signals}:
                by_detector[detector] = by_detector.get(detector, 0) + 1
        report.append({
            "sensitivity": sensitivity, "days": len(rows), "flagged_days": sorted(flagged),
            "high_days": sorted(day for day, signals in flagged.items() if any(s["severity"] == "high" for s in signals)),
            "by_detector": dict(sorted(by_detector.items())),
        })
    return report


def _typical_workday(rows: list[dict[str, Any]], index: int, kinds: dict[str, str]) -> float | None:
    history = rolling_history(rows, index, WINDOW_DAYS)
    totals = [row["tokens"]["total"] for row in history if kinds.get(row["date"]) == "workday" and row.get("tokens")]
    return float(median(totals)) if len(totals) >= MIN_WORKDAYS else None


def _targets(rows: list[dict[str, Any]], index: int, scenario: Scenario, kinds: dict[str, str]) -> list[int] | None:
    """Indexes the scenario touches when it starts at ``index``; None when it does not fit there."""
    if scenario.days == 1:
        return [index]
    workdays = [i for i in range(index, len(rows))
                if kinds[rows[i]["date"]] == "workday" and rows[i].get("tokens") and rows[i].get("active_users")]
    if not workdays or workdays[0] != index or len(workdays) < scenario.days:
        return None
    return workdays[:scenario.days]


def inject(rows: list[dict[str, Any]], targets: list[int], scenario: Scenario, typical: float) -> list[dict[str, Any]]:
    """A copy of ``rows`` with the scenario's misuse added to the ``targets`` rows."""
    changed = copy.deepcopy(rows)
    extra = round(typical * scenario.tokens)
    for index in targets:
        row = changed[index]
        row["tokens"][scenario.product] += extra
        row["tokens"]["total"] += extra
        row["active_users"][scenario.product] += scenario.users
    return changed


def detection_rates(rows: list[dict[str, Any]], detectors: DetectorSet,
                    sensitivities: tuple[float, ...] = SENSITIVITIES, scenarios: tuple[Scenario, ...] = SCENARIOS,
                    today: str | None = None, level_shifts: bool = False) -> list[dict[str, Any]]:
    """Per scenario and sensitivity: in what share of attempts the injected misuse gets flagged.

    Only days that are not flagged without the injection count, so the rate measures what the
    misuse itself triggers. Days keep the kind (workday/holiday) they had before the injection:
    the question is whether the amounts stand out, not whether extra users reclassify the day.
    A scenario lasting several days counts as noticed when any of its days is newly flagged.
    """
    kinds = {day: value["kind"] for day, value in classify_days(rows).items()}
    report = []
    for scenario in scenarios:
        line: dict[str, Any] = {"key": scenario.key, "label": scenario.label, "rates": {}}
        for sensitivity in sensitivities:
            already = _flagged_days(rows, detectors, sensitivity, today, level_shifts=level_shifts)
            tried = detected = 0
            for index, row in enumerate(rows):
                if row.get("tokens") is None or row.get("active_users") is None:
                    continue
                if scenario.holidays_only and kinds[row["date"]] != "holiday":
                    continue
                typical = _typical_workday(rows, index, kinds)
                targets = _targets(rows, index, scenario, kinds)
                if typical is None or targets is None or (scenario.days == 1 and row["date"] in already):
                    continue
                tried += 1
                flagged = _flagged_days(inject(rows, targets, scenario, typical), detectors, sensitivity, today, kinds, level_shifts)
                # A run of days is reported at its first day, which can lie a little before the misuse began.
                first = (date.fromisoformat(row["date"]) - timedelta(days=LEAD_DAYS)).isoformat()
                last = rows[targets[-1]]["date"]
                detected += any(first <= day <= last and day not in already for day in flagged)
            line["rates"][sensitivity] = {"tried": tried, "detected": detected}
        report.append(line)
    return report


def render(rows: list[dict[str, Any]], detectors: DetectorSet, today: str | None = None) -> str:
    """The evaluation as plain text: the day-by-day rules alone, then with level shifts added."""
    if not rows:
        return "ワークスペースのデータがありません。"
    lines = [f"対象: {rows[0]['date']} 〜 {rows[-1]['date']}（{len(rows)}日）。この期間に不正利用はなかったものとして評価します。"]
    for level_shifts, title in ((False, "A. 1日ごとの判定だけ（既定）"), (True, "B. 「変化点検出」を有効にした場合")):
        lines += ["", f"===== {title} ====="]
        lines += _render_part(rows, detectors, today, level_shifts)
    return "\n".join(lines)


def _render_part(rows: list[dict[str, Any]], detectors: DetectorSet, today: str | None, level_shifts: bool) -> list[str]:
    lines = ["1. 誤検出: 不正のない期間で「要確認」（参考を除く）になった日"]
    for entry in false_alarms(rows, detectors, today=today, level_shifts=level_shifts):
        share = len(entry["flagged_days"]) / entry["days"]
        detail = "、".join(f"{name} {count}日" for name, count in entry["by_detector"].items()) or "なし"
        lines.append(f"  感度 {entry['sensitivity']:<4}: {len(entry['flagged_days']):>2}日 / {entry['days']}日（{share:.0%}）"
                     f"  うち重要度「高」{len(entry['high_days'])}日  [{detail}]")
        if entry["flagged_days"]:
            lines.append("             " + " ".join(day[5:] for day in entry["flagged_days"]))
    for title, scenarios in (
        ("2. 検出力（1日だけ）: 1日だけ不正利用を足したとき、その日が「要確認」になる割合", SCENARIOS),
        ("3. 検出力（少しずつ続く）: 平日に毎日足したとき、その期間のどこかが「要確認」になる割合", SUSTAINED),
    ):
        lines += ["", title]
        lines.append("  " + " " * 2 + "".join(f"感度{s:<5}" for s in SENSITIVITIES) + " シナリオ")
        for line in detection_rates(rows, detectors, scenarios=scenarios, today=today, level_shifts=level_shifts):
            cells = "".join(
                f"{(r['detected'] / r['tried']):>5.0%}    " if r["tried"] else "   -     " for r in line["rates"].values())
            lines.append(f"  {cells} {line['label']}")
    lines += ["", "  足した量は「直前28日の平日の総トークン中央値」に対する倍率です。もともと要確認の日は試行から除いています。"]
    return lines
