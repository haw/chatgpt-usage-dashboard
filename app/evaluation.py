"""Check the detection rules against a period that is known to be clean.

Two questions decide whether a rule set is usable:

1. How often does it cry wolf? Every day it flags in a period without abuse is a day the analyst
   looks at for nothing.
2. Would it notice abuse? Synthetic misuse is added to one day at a time and the rules are run
   again; the share of days on which the addition is flagged is the detection rate.

Both are reported for several sensitivities so the trade-off is visible. The amounts injected are
multiples of the workspace's own typical workday, so the result does not depend on its size.

    python -m app evaluate            # uses the stored workspace data and config/detectors.toml
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from statistics import median
from typing import Any

from app.detectors import DetectionContext, DetectorSet
from app.detectors.calendar import classify_days
from app.detectors.stats import rolling_history

SENSITIVITIES = (0.5, 1.0, 1.4, 2.0)
WINDOW_DAYS = 28
MIN_WORKDAYS = 5


@dataclass(frozen=True)
class Scenario:
    """Misuse added to a single day. ``tokens`` is a multiple of a typical workday's total."""

    key: str
    label: str
    tokens: float = 0.0
    users: int = 0
    product: str = "codex"
    holidays_only: bool = False


SCENARIOS = (
    Scenario("takeover_small", "既存アカウントの乗っ取り（平日1日分の半分を消費）", tokens=0.5),
    Scenario("takeover_medium", "既存アカウントの乗っ取り（平日1日分を消費）", tokens=1.0),
    Scenario("takeover_large", "既存アカウントの乗っ取り（平日3日分を消費）", tokens=3.0),
    Scenario("takeover_chat", "既存アカウントの乗っ取り（Chatで平日1日分を消費）", tokens=1.0, product="chat"),
    Scenario("new_account", "不正なアカウント1つが平日1日分を消費", tokens=1.0, users=1),
    Scenario("holiday_use", "休日に不正なアカウント1つが平日1日分の半分を消費", tokens=0.5, users=1, holidays_only=True),
    Scenario("accounts_only", "アカウントが3つ増える（利用量は増えない）", users=3, product="chat"),
)


def _flagged_days(rows: list[dict[str, Any]], detectors: DetectorSet, sensitivity: float, today: str | None,
                  overrides: dict[str, str] | None = None) -> dict[str, list[dict[str, Any]]]:
    """Dates with at least one signal above the line (not "info"), with those signals."""
    days = classify_days(rows, overrides)
    ctx = DetectionContext(rows=rows, scope="workspace", day_kinds={d: v["kind"] for d, v in days.items()},
                           sensitivity=sensitivity, today=today)
    operations = {d.id for d in detectors.detectors if d.group == "operations"}
    result: dict[str, list[dict[str, Any]]] = {}
    for signal in detectors.run(ctx):
        if signal["severity"] != "info" and signal["detector"] not in operations:
            result.setdefault(signal["date"], []).append(signal)
    return result


def false_alarms(rows: list[dict[str, Any]], detectors: DetectorSet, sensitivities: tuple[float, ...] = SENSITIVITIES,
                 today: str | None = None) -> list[dict[str, Any]]:
    """Per sensitivity: which days of the (clean) data are flagged, and by which detectors."""
    report = []
    for sensitivity in sensitivities:
        flagged = _flagged_days(rows, detectors, sensitivity, today)
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


def inject(rows: list[dict[str, Any]], index: int, scenario: Scenario, typical: float) -> list[dict[str, Any]]:
    """A copy of ``rows`` with the scenario's misuse added to ``rows[index]``."""
    changed = copy.deepcopy(rows)
    row = changed[index]
    extra = round(typical * scenario.tokens)
    row["tokens"][scenario.product] += extra
    row["tokens"]["total"] += extra
    row["active_users"][scenario.product] += scenario.users
    return changed


def detection_rates(rows: list[dict[str, Any]], detectors: DetectorSet,
                    sensitivities: tuple[float, ...] = SENSITIVITIES, scenarios: tuple[Scenario, ...] = SCENARIOS,
                    today: str | None = None) -> list[dict[str, Any]]:
    """Per scenario and sensitivity: on what share of days the injected misuse gets flagged.

    Only days that are not flagged without the injection count, so the rate measures what the
    misuse itself triggers. The day keeps the kind (workday/holiday) it had before the injection:
    the question is whether the amounts stand out, not whether extra users reclassify the day.
    """
    kinds = {day: value["kind"] for day, value in classify_days(rows).items()}
    report = []
    for scenario in scenarios:
        line: dict[str, Any] = {"key": scenario.key, "label": scenario.label, "rates": {}}
        for sensitivity in sensitivities:
            already = _flagged_days(rows, detectors, sensitivity, today)
            tried = detected = 0
            for index, row in enumerate(rows):
                if row.get("tokens") is None or row.get("active_users") is None or row["date"] in already:
                    continue
                if scenario.holidays_only and kinds[row["date"]] != "holiday":
                    continue
                typical = _typical_workday(rows, index, kinds)
                if typical is None:
                    continue
                tried += 1
                flagged = _flagged_days(inject(rows, index, scenario, typical), detectors, sensitivity, today, kinds)
                detected += row["date"] in flagged
            line["rates"][sensitivity] = {"tried": tried, "detected": detected}
        report.append(line)
    return report


def render(rows: list[dict[str, Any]], detectors: DetectorSet, today: str | None = None) -> str:
    """The evaluation as plain text."""
    if not rows:
        return "ワークスペースのデータがありません。"
    lines = [f"対象: {rows[0]['date']} 〜 {rows[-1]['date']}（{len(rows)}日）。この期間に不正利用はなかったものとして評価します。", ""]
    lines.append("1. 誤検出: 不正のない期間で「要確認」（参考を除く）になった日")
    for entry in false_alarms(rows, detectors, today=today):
        share = len(entry["flagged_days"]) / entry["days"]
        detail = "、".join(f"{name} {count}日" for name, count in entry["by_detector"].items()) or "なし"
        lines.append(f"  感度 {entry['sensitivity']:<4}: {len(entry['flagged_days']):>2}日 / {entry['days']}日（{share:.0%}）"
                     f"  うち重要度「高」{len(entry['high_days'])}日  [{detail}]")
        if entry["flagged_days"]:
            lines.append("             " + " ".join(day[5:] for day in entry["flagged_days"]))
    lines += ["", "2. 検出力: 1日だけ不正利用を足したとき、その日が「要確認」になる割合（もともと要確認の日を除く）"]
    rates = detection_rates(rows, detectors, today=today)
    lines.append("  " + " " * 2 + "".join(f"感度{s:<5}" for s in SENSITIVITIES) + " シナリオ")
    for line in rates:
        cells = "".join(
            f"{(r['detected'] / r['tried']):>5.0%}    " if r["tried"] else "   -     " for r in line["rates"].values())
        lines.append(f"  {cells} {line['label']}")
    lines += ["", "  足した量は「直前28日の平日の総トークン中央値」に対する倍率です。"]
    return "\n".join(lines)
