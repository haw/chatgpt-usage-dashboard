from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import httpx


class AnalyticsAPIError(RuntimeError):
    pass


class AnalyticsClient:
    def __init__(self, url: str, key: str, timeout: float = 30, max_retries: int = 3):
        self.url = url
        self.key = key
        self.timeout = timeout
        self.max_retries = max_retries

    def pages(self, start_time: int, end_time: int) -> Iterator[dict[str, Any]]:
        page: str | None = None
        seen_pages: set[str] = set()
        while True:
            params: dict[str, Any] = {
                "start_time": start_time,
                "end_time": end_time,
                "limit": 100,
            }
            if page:
                params["page"] = page
            payload = self._get(params)
            yield payload
            has_more = bool(payload.get("has_more"))
            next_page = payload.get("next_page") or payload.get("next")
            if not has_more or not next_page:
                break
            page = str(next_page)
            if page in seen_pages:
                raise AnalyticsAPIError("The API returned a repeated pagination cursor.")
            seen_pages.add(page)

    def _get(self, params: dict[str, Any]) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.key}", "Accept": "application/json"}
        for attempt in range(self.max_retries + 1):
            try:
                response = httpx.get(self.url, headers=headers, params=params, timeout=self.timeout)
            except httpx.RequestError as exc:
                if attempt >= self.max_retries:
                    raise AnalyticsAPIError(f"Could not connect to Analytics API: {exc}") from exc
                time.sleep(2**attempt)
                continue
            if response.status_code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                time.sleep(min(2**attempt, 8))
                continue
            if response.status_code in (401, 403):
                raise AnalyticsAPIError(
                    f"Analytics API returned {response.status_code}. Check that the key is workspace-scoped, "
                    "has enterprise.analytics.usage.read, and the endpoint is enabled."
                )
            if response.status_code == 404:
                raise AnalyticsAPIError(
                    "Analytics API endpoint was not found (404). Confirm OPENAI_ANALYTICS_URL in the "
                    "authenticated ChatGPT Admin API reference."
                )
            try:
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPStatusError, ValueError) as exc:
                body = response.text[:300].replace(self.key, "[REDACTED]")
                raise AnalyticsAPIError(f"Analytics API request failed ({response.status_code}): {body}") from exc
            if not isinstance(payload, dict):
                raise AnalyticsAPIError("Analytics API returned an unexpected non-object response.")
            return payload
        raise AssertionError("unreachable")

