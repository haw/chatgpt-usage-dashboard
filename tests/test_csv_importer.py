import pytest

from app.csv_importer import CSVImportError, parse_and_join


def csv_bytes(rows: list[str]) -> bytes:
    return ("Start Time,End Time,Chat,Codex,Work\n" + "\n".join(rows) + "\n").encode()


def test_parse_and_join_accepts_timestamp_and_date():
    active = csv_bytes(["2026-09-01T00:00:00Z,2026-09-02T00:00:00Z,5,3,1"])
    tokens = csv_bytes(["2026-09-01,2026-09-02,100,200,50"])

    assert parse_and_join(active, tokens) == [{
        "date": "2026-09-01",
        "end_date": "2026-09-02",
        "active_users": {"chat": 5, "codex": 3, "work": 1},
        "tokens": {"chat": 100, "codex": 200, "work": 50, "total": 350},
    }]


def test_parse_and_join_rejects_mismatched_dates():
    active = csv_bytes(["2026-09-01,2026-09-02,5,3,1"])
    tokens = csv_bytes(["2026-09-02,2026-09-03,100,200,50"])
    with pytest.raises(CSVImportError, match="日付が一致しません"):
        parse_and_join(active, tokens)


@pytest.mark.parametrize("bad_value", ["-1", "1.5", "unknown"])
def test_parse_rejects_invalid_counts(bad_value: str):
    active = csv_bytes([f"2026-09-01,2026-09-02,{bad_value},3,1"])
    tokens = csv_bytes(["2026-09-01,2026-09-02,100,200,50"])
    with pytest.raises(CSVImportError):
        parse_and_join(active, tokens)
