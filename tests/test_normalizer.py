import json
from pathlib import Path

from app.normalizer import normalize_pages


def test_normalizes_bucketed_response():
    fixture = Path("tests/fixtures/analytics_page.json")
    rows = normalize_pages([json.loads(fixture.read_text(encoding="utf-8"))])

    assert len(rows) == 2
    assert rows[0]["date"] == "2026-09-21"
    assert rows[0]["user_id"] == "user-001"
    assert rows[0]["activity"] == 1512
    assert rows[1]["product"] == "work"


def test_coalesces_same_user_date_and_product():
    page = {"data": [{"date": "2026-09-01", "results": [
        {"user_id": "u1", "product": "chatgpt", "messages": 2},
        {"user_id": "u1", "product": "chatgpt", "messages": 3},
    ]}]}
    rows = normalize_pages([page])
    assert len(rows) == 1
    assert rows[0]["activity"] == 5

