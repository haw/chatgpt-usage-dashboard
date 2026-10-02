import json
from pathlib import Path

from app.detectors import DetectionContext, build_detector_set
from app.detectors.builtin.dau_increase import DauIncrease
from app.detectors.builtin.holiday_usage import HolidayUsage
from app.detectors.builtin.stale_data import StaleData
from app.detectors.builtin.tokens_per_user import TokensPerUser
from app.detectors.calendar import classify_days
from app.json_importer import parse_workspace_json

FIXTURES = Path(__file__).parent / "fixtures"
CONFIG = Path(__file__).parent.parent / "config" / "detectors.toml"


def usage(day: int, chat_tokens: int = 1000, chat_dau: int = 5) -> dict:
    tokens = {"chat": chat_tokens, "codex": 20, "work": 10}
    return {
        "date": f"2026-09-{day:02d}",
        "active_users": {"chat": chat_dau, "codex": 3, "work": 1},
        "tokens": {**tokens, "total": sum(tokens.values())},
    }


def context(rows: list[dict], **kwargs) -> DetectionContext:
    days = classify_days(rows)
    return DetectionContext(rows=rows, day_kinds={d: v["kind"] for d, v in days.items()}, **kwargs)


def test_tokens_per_user_flags_few_users_with_many_tokens():
    # 2026-09-14 (Mon) .. 09-25 (Fri): 5 users x 10M chat tokens, then 1 user burning 50M
    rows = [usage(day, chat_tokens=50_000_000 + (day % 3) * 1_000_000, chat_dau=5) for day in range(14, 26)]
    rows.append(usage(28, chat_tokens=50_000_000, chat_dau=1))
    signals = TokensPerUser().detect(context(rows))
    assert [(s["date"], s["product"], s["severity"]) for s in (x.to_dict() for x in signals)] == [
        ("2026-09-28", "chat", "high")]
    assert signals[0].value == 50_000_000 and signals[0].baseline == 10_200_000
    assert "1人で" in signals[0].reason
    # the same total with the usual head-count is normal
    rows[-1] = usage(28, chat_tokens=50_000_000, chat_dau=5)
    assert TokensPerUser().detect(context(rows)) == []


def test_dau_increase_reports_one_extra_user_as_info():
    rows = [usage(day, chat_dau=5) for day in range(14, 26)] + [usage(28, chat_dau=6)]
    signals = [s.to_dict() for s in DauIncrease().detect(context(rows))]
    assert [(s["date"], s["product"], s["severity"], s["value"], s["baseline"]) for s in signals] == [
        ("2026-09-28", "chat", "info", 6, 5)]
    rows[-1] = usage(28, chat_dau=5)
    assert DauIncrease().detect(context(rows)) == []


def test_holiday_usage_compares_holidays_with_workday_median():
    rows = [usage(day, chat_tokens=100_000_000) for day in range(14, 19)]  # Mon-Fri
    rows.append(usage(19, chat_tokens=60_000_000, chat_dau=1))  # Saturday at 60% of a workday
    rows.append(usage(20, chat_tokens=15_000_000, chat_dau=1))  # Sunday, quiet (15% of a workday)
    signals = [s.to_dict() for s in HolidayUsage().detect(context(rows))]
    assert [s["date"] for s in signals] == ["2026-09-19"]
    assert signals[0]["baseline"] == 100_000_030 and "60%" in signals[0]["reason"]
    assert HolidayUsage().detect(context(rows, sensitivity=0.5)) == []
    assert len(HolidayUsage().detect(context(rows, sensitivity=4))) == 2


def test_stale_data_warns_only_when_the_latest_day_is_old():
    rows = [usage(day) for day in range(1, 4)]
    assert StaleData().detect(context(rows, today="2026-09-06")) == []
    signals = StaleData().detect(context(rows, today="2026-09-10"))
    assert len(signals) == 1 and signals[0].value == 7 and signals[0].date == "2026-09-03"
    assert StaleData().detect(context(rows, today="2026-09-10", period_wide=True)) == []


def load_fixture_rows() -> list[dict]:
    daily: dict[str, dict] = {}
    for name, metric in (("workspace-tokens-2026-09.json", "tokens"), ("workspace-active-users-2026-09.json", "active_users")):
        _, parsed = parse_workspace_json((FIXTURES / name).read_bytes())
        for day, source in parsed.items():
            row = daily.setdefault(day, {"date": day})
            row[metric] = dict(source["values"])
            if metric == "tokens":
                row[metric]["total"] = sum(source["values"].values())
    return [daily[day] for day in sorted(daily)]


def test_real_september_data_with_shipped_config():
    """Regression on the real September export: the few-users/huge-tokens day must surface,
    the public holidays must not be reported as DAU drops, and sensitivity must be monotonic."""
    rows = load_fixture_rows()
    detectors = build_detector_set(CONFIG)
    assert detectors.errors == []
    days = classify_days(rows)
    assert {days[d]["source"] for d in ("2026-09-21", "2026-09-22", "2026-09-23")} == {"inferred"}

    def run(sensitivity: float) -> list[dict]:
        ctx = DetectionContext(rows=rows, day_kinds={d: v["kind"] for d, v in days.items()},
                               sensitivity=sensitivity, today="2026-10-02")
        return detectors.run(ctx)

    signals = run(1.0)
    codex_per_user = [s for s in signals if s["detector"] == "tokens_per_user" and s["date"] == "2026-10-01" and s["product"] == "codex"]
    assert codex_per_user and codex_per_user[0]["severity"] == "high"
    assert not [s for s in signals if s["type"] == "dau_drop" and s["date"] == "2026-09-21"]
    assert {s["date"] for s in signals if s["detector"] == "holiday_usage"} >= {"2026-09-21", "2026-09-22", "2026-09-23"}
    assert not [s for s in signals if s["detector"] == "stale_data"]
    strong = [s for s in signals if s["severity"] != "info"]
    assert len(run(0.5)) <= len(signals) <= len(run(2.0))
    assert len([s for s in run(0.5) if s["severity"] != "info"]) <= len(strong)


def test_fixture_files_are_valid_exports():
    for name in ("workspace-tokens-2026-09.json", "workspace-active-users-2026-09.json"):
        document = json.loads((FIXTURES / name).read_text())
        assert document["chart_key"] in {"tokens", "active-users"}
