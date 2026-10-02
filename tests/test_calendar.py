from app.detectors.calendar import classify_days, parse_override_list


def row(day: str, dau: int | None = None, tokens: int | None = None) -> dict:
    result = {"date": day}
    if dau is not None:
        result["active_users"] = {"chat": dau, "codex": max(dau - 2, 0), "work": 1}
    if tokens is not None:
        result["tokens"] = {"chat": tokens, "codex": 0, "work": 0, "total": tokens}
    return result


def test_weekends_are_holidays_and_quiet_weekdays_are_inferred():
    rows = [
        row("2026-09-14", 10), row("2026-09-15", 11), row("2026-09-16", 9), row("2026-09-17", 10),
        row("2026-09-18", 10), row("2026-09-19", 3), row("2026-09-20", 2),
        row("2026-09-21", 4), row("2026-09-22", 5), row("2026-09-23", 5), row("2026-09-24", 10),
    ]
    days = classify_days(rows)
    assert days["2026-09-19"] == {"kind": "holiday", "source": "weekend"}
    assert days["2026-09-21"] == {"kind": "holiday", "source": "inferred"}
    assert days["2026-09-23"] == {"kind": "holiday", "source": "inferred"}
    assert days["2026-09-24"] == {"kind": "workday", "source": "weekday"}


def test_overrides_win_and_tokens_are_the_fallback_when_dau_is_missing():
    rows = [row(f"2026-09-{day:02d}", tokens=100_000_000) for day in (14, 15, 16, 17, 18)]
    rows.append(row("2026-09-21", tokens=10_000_000))
    rows.append(row("2026-09-22", tokens=90_000_000))
    days = classify_days(rows, {"2026-09-22": "holiday", "2026-09-19": "workday", "2026-09-21": "bogus"})
    assert days["2026-09-21"]["source"] == "inferred"
    assert days["2026-09-22"] == {"kind": "holiday", "source": "override"}


def test_too_few_samples_fall_back_to_the_calendar():
    rows = [row("2026-09-14", 10), row("2026-09-15", 1)]
    days = classify_days(rows)
    assert days["2026-09-15"] == {"kind": "workday", "source": "weekday"}
    assert classify_days(rows, infer=False)["2026-09-15"]["source"] == "weekday"


def test_parse_override_list():
    assert parse_override_list(" 2026-12-29,2026-12-30 ", "2026-09-22") == {
        "2026-12-29": "holiday", "2026-12-30": "holiday", "2026-09-22": "workday",
    }
    assert parse_override_list(None, "") == {}
    try:
        parse_override_list("2026-13-01", None)
    except ValueError as exc:
        assert "2026-13-01" in str(exc)
    else:
        raise AssertionError("expected ValueError")
