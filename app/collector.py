from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from app.client import AnalyticsClient
from app.normalizer import normalize_pages
from app.storage import LocalStorage


def collect(client: AnalyticsClient, storage: LocalStorage, days: int = 7, end_date: date | None = None) -> dict[str, Any]:
    if not 1 <= days <= 90:
        raise ValueError("days must be between 1 and 90")
    exclusive_date = end_date or datetime.now(timezone.utc).date()
    start_date = exclusive_date - timedelta(days=days)
    start_time = int(datetime.combine(start_date, time.min, tzinfo=timezone.utc).timestamp())
    end_time = int(datetime.combine(exclusive_date, time.min, tzinfo=timezone.utc).timestamp())
    run_id = storage.create_run()
    started_at = datetime.now(timezone.utc).isoformat()
    pages: list[dict[str, Any]] = []
    try:
        for page_number, page in enumerate(client.pages(start_time, end_time), start=1):
            storage.save_raw_page(run_id, page_number, page)
            pages.append(page)
        rows = normalize_pages(pages)
        total_rows = storage.merge_usage(rows)
        state = {
            "status": "success", "run_id": run_id, "started_at": started_at,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "start_date": start_date.isoformat(), "end_date": (exclusive_date - timedelta(days=1)).isoformat(),
            "pages": len(pages), "records_received": len(rows), "records_stored": total_rows,
        }
        if pages and not rows and any(page.get("data") or page.get("results") for page in pages):
            state["warning"] = "API data was saved, but no rows matched the current normalizer. Inspect raw files."
        storage.save_state(state)
        return state
    except Exception as exc:
        storage.save_state({"status": "error", "run_id": run_id, "started_at": started_at,
                            "completed_at": datetime.now(timezone.utc).isoformat(), "error": str(exc)})
        raise

