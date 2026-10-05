"""Properties the detection rules were tuned for on a period without abuse (see app/evaluation.py)."""
from app.detectors import DetectionContext, DetectorSet
from app.detectors.builtin.dau_change import DauChange
from app.detectors.builtin.dau_increase import DauIncrease
from app.detectors.builtin.holiday_usage import HolidayUsage
from app.detectors.builtin.token_spike import TokenSpike
from app.detectors.builtin.tokens_per_user import TokensPerUser
from app.detectors.calendar import classify_days
from app.detectors.stats import count_baseline, ratio_baseline, ratio_score, ratio_threshold
from app.evaluation import SCENARIOS, SUSTAINED, detection_rates, false_alarms, render

M = 1_000_000
WOBBLE = (1.0, 1.3, 0.8, 1.1, 0.7, 1.5, 0.9, 1.2, 0.85, 1.05)  # ordinary day-to-day variation, no randomness


def day(index: int) -> str:
    """index 0 is Monday 2026-06-01."""
    from datetime import date, timedelta

    return (date(2026, 6, 1) + timedelta(days=index)).isoformat()


def workspace(days: int, level=lambda index: 100 * M, users=lambda index: 10) -> list[dict]:
    """A workspace that uses ``level(index)`` tokens on workdays (a fifth of it at weekends)."""
    rows = []
    for index in range(days):
        weekend = index % 7 in (5, 6)
        total = round(level(index) * WOBBLE[index % len(WOBBLE)] * (0.2 if weekend else 1.0))
        head = max(round(users(index) * (0.3 if weekend else 1.0)), 1)
        rows.append({"date": day(index), "active_users": {"chat": head, "codex": max(head - 2, 1), "work": 1},
                     "tokens": {"chat": total * 2 // 5, "codex": total * 3 // 5, "work": 0, "total": total}})
    return rows


def context(rows: list[dict], **kwargs) -> DetectionContext:
    kinds = classify_days(rows)
    return DetectionContext(rows=rows, day_kinds={d: v["kind"] for d, v in kinds.items()}, **kwargs)


def flagged(detector, rows: list[dict], **kwargs) -> list[str]:
    return sorted({s.date for s in detector.detect(context(rows, **kwargs)) if s.severity != "info"})


def all_detectors() -> DetectorSet:
    return DetectorSet([TokenSpike(), TokensPerUser(), DauChange(), DauIncrease(), HolidayUsage()], [])


def test_ratio_statistics():
    typical, spread = ratio_baseline([100, 100, 100, 100, 100], scale=100, min_spread=0.25)
    assert round(typical, 6) == 100 and spread == 0.25  # identical days: the minimum spread applies
    assert ratio_score(100, typical, spread, 100) == 0
    line = ratio_threshold(typical, spread, 100, 3.5)
    assert round(ratio_score(line, typical, spread, 100), 6) == 3.5
    assert 370 < line < 390  # 200 * e^0.875 - 100: almost four times the usual amount
    # going from next to nothing to a small amount is not "20 times" at this scale
    assert ratio_score(2, 0.1, 0.25, 100) < 0.1
    wide, wide_spread = ratio_baseline([50, 100, 200, 400, 800], scale=1, min_spread=0.25)
    assert round(wide) == 200 and wide_spread > 0.9  # days that differ by factors widen the line
    assert count_baseline([10, 10, 10, 10], min_spread=1.0) == (10.0, 1.0)


def test_ordinary_variation_is_not_flagged():
    rows = workspace(56)
    for detector in (TokenSpike(), TokensPerUser(), DauChange(), HolidayUsage()):
        assert flagged(detector, rows) == [], detector.id


def test_a_day_far_above_the_usual_is_flagged_and_graded():
    rows = workspace(56)
    rows[45]["tokens"] = {"chat": 40 * M, "codex": 460 * M, "work": 0, "total": 500 * M}  # five workdays' worth
    assert flagged(TokenSpike(), rows) == [day(45)]
    severities = {s.product: s.severity for s in TokenSpike().detect(context(rows)) if s.date == day(45) and s.severity != "info"}
    assert severities == {None: "medium", "codex": "medium"}
    rows[45]["tokens"] = {"chat": 40 * M, "codex": 2460 * M, "work": 0, "total": 2500 * M}
    assert {s.severity for s in TokenSpike().detect(context(rows)) if s.date == day(45) and s.product is None} == {"high"}
    # the analyst's lens: a doubled day only shows when the sensitivity is raised
    rows[45]["tokens"] = {"chat": 40 * M, "codex": 230 * M, "work": 0, "total": 270 * M}
    assert flagged(TokenSpike(), rows) == []
    assert day(45) in flagged(TokenSpike(), rows, sensitivity=2.0)


def test_growth_becomes_the_new_baseline_instead_of_alarming_forever():
    # usage grows fivefold in week 5 and stays there
    rows = workspace(84, level=lambda index: (20 if index < 28 else 100) * M)
    days = flagged(TokenSpike(), rows)
    assert days[0] == day(28) and len(days) <= 3          # reported when it starts, then accepted
    shifts = [s for s in TokenSpike().detect(context(rows)) if s.type == "level_shift" and s.product is None]
    assert [(s.date, s.severity) for s in shifts] == [(day(28), "high")]
    assert shifts[0].span_days == 2 and shifts[0].baseline < 25 * M < 80 * M < shifts[0].value
    # without level tracking the rolling baseline needs a couple of weeks to catch up
    slow = flagged(TokenSpike({"shift_limit": 0}), rows)
    assert len(days) < len(slow) <= 10 and all(d < day(28 + 21) for d in slow), slow
    # and with exclude_anomalies on top the old level stays the reference for as long as it is in the window
    sticky = flagged(TokenSpike({"shift_limit": 0, "exclude_anomalies": True}), rows)
    assert len(sticky) > len(slow) and sticky[-1] > slow[-1]


def test_small_misuse_that_goes_on_is_reported_once_as_a_level_shift():
    rows = workspace(70)
    for index in range(42, 47):  # Mon-Fri of week 7: one more ordinary workday's worth, every day
        rows[index]["tokens"]["codex"] += 100 * M
        rows[index]["tokens"]["total"] += 100 * M
    assert flagged(TokenSpike({"shift_limit": 0}), rows) == []  # no single day crosses the line
    signals = [s for s in TokenSpike().detect(context(rows)) if s.severity != "info"]
    assert {(s.type, s.date) for s in signals} == {("level_shift", day(42))}
    assert "codex" in {s.product for s in signals} and all(s.span_days >= 3 for s in signals)
    assert "水準の変化" in signals[0].reason
    # one very high day is a spike, not a change of level
    rows = workspace(70)
    rows[45]["tokens"] = {"chat": 40 * M, "codex": 460 * M, "work": 0, "total": 500 * M}
    assert {s.type for s in TokenSpike().detect(context(rows)) if s.severity != "info"} == {"token_spike"}


def test_more_people_every_day_is_a_level_shift_but_one_more_person_is_not():
    rows = workspace(70)
    for index in range(42, 70):
        if index % 7 < 5:
            rows[index]["active_users"]["chat"] += 3
    signals = [s for s in DauChange().detect(context(rows)) if s.severity != "info"]
    assert [(s.type, s.date, s.baseline, s.value) for s in signals] == [("dau_level_shift", day(42), 10, 13)]
    assert flagged(DauChange({"shift_limit": 0}), rows) == []
    rows = workspace(70)
    for index in range(42, 70):
        if index % 7 < 5:
            rows[index]["active_users"]["chat"] += 1
    assert flagged(DauChange(), rows) == []


def test_small_amounts_do_not_count_as_spikes():
    rows = workspace(56)
    for row in rows:
        row["tokens"]["work"] = 100_000
        row["tokens"]["total"] += 100_000
    rows[45]["tokens"]["work"] = 3 * M  # thirty times the usual Work usage, 3% of a day's total
    rows[45]["tokens"]["total"] += 3 * M - 100_000
    assert flagged(TokenSpike(), rows) == [] and flagged(TokensPerUser(), rows) == []
    rows[45]["tokens"]["work"] = 400 * M  # Work alone is suddenly four ordinary days
    rows[45]["tokens"]["total"] += 397 * M
    assert flagged(TokenSpike(), rows) == [day(45)] and flagged(TokensPerUser(), rows) == [day(45)]


def test_dau_needs_more_than_one_or_two_people_after_a_flat_history():
    rows = workspace(42)
    rows[38]["active_users"]["chat"] = 12  # +2 after weeks of exactly 10
    assert flagged(DauChange(), rows) == []
    rows[38]["active_users"]["chat"] = 15  # +5
    assert flagged(DauChange(), rows) == [day(38)]
    assert [s.type for s in DauChange().detect(context(rows)) if s.severity != "info"] == ["dau_spike"]


def test_a_growing_workspace_keeps_its_early_weekdays_as_workdays():
    # 4 daily users at first, 12 later; one public holiday (index 43, a Wednesday) with 5 users
    rows = workspace(63, users=lambda index: 4 if index < 21 else 12)
    rows[43]["active_users"] = {"chat": 5, "codex": 3, "work": 1}
    kinds = classify_days(rows)
    assert {kinds[day(index)]["source"] for index in range(21) if index % 7 < 5} == {"weekday"}
    assert kinds[day(43)] == {"kind": "holiday", "source": "inferred"}
    assert kinds[day(44)] == {"kind": "workday", "source": "weekday"}


def test_evaluation_reports_false_alarms_and_what_misuse_would_be_noticed():
    rows = workspace(70)
    detectors = all_detectors()
    alarms = {entry["sensitivity"]: entry for entry in false_alarms(rows, detectors, (1.0, 2.0), today=day(70))}
    assert alarms[1.0]["flagged_days"] == [] and alarms[1.0]["days"] == 70
    assert len(alarms[2.0]["flagged_days"]) >= len(alarms[1.0]["flagged_days"])
    rates = {line["key"]: line["rates"] for line in detection_rates(rows, detectors, (1.0, 2.0), SCENARIOS, today=day(70))}
    large, small = rates["takeover_large"], rates["takeover_small"]
    assert large[1.0]["tried"] > 20 and large[1.0]["detected"] / large[1.0]["tried"] > 0.8
    assert small[1.0]["detected"] <= large[1.0]["detected"]  # more misuse is never harder to notice
    assert small[2.0]["detected"] >= small[1.0]["detected"]  # nor is a higher sensitivity
    assert rates["holiday_use"][1.0]["tried"] < large[1.0]["tried"]  # only holidays are tried
    slow = {line["key"]: line["rates"][1.0] for line in detection_rates(rows, detectors, (1.0,), SUSTAINED, today=day(70))}
    spikes_only = DetectorSet([TokenSpike({"shift_limit": 0}), TokensPerUser({"shift_limit": 0})], [])
    without = {line["key"]: line["rates"][1.0] for line in detection_rates(rows, spikes_only, (1.0,), SUSTAINED, today=day(70))}
    assert slow["slow_one_5"]["detected"] / slow["slow_one_5"]["tried"] > 0.8 > 0.2 > (
        without["slow_one_5"]["detected"] / without["slow_one_5"]["tried"])
    text = render(rows, detectors, today=day(70))
    assert "誤検出" in text and "検出力" in text and "少しずつ続く" in text and "70日" in text
    assert render([], detectors) == "ワークスペースのデータがありません。"
