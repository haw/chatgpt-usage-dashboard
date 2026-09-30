import respx
from httpx import Response

from app.client import AnalyticsClient, AnalyticsAPIError


@respx.mock
def test_follows_pagination():
    route = respx.get("https://example.test/usage").mock(side_effect=[
        Response(200, json={"data": [], "has_more": True, "next_page": "next"}),
        Response(200, json={"data": [], "has_more": False, "next_page": None}),
    ])
    pages = list(AnalyticsClient("https://example.test/usage", "secret").pages(1, 2))
    assert len(pages) == 2
    assert route.call_count == 2


@respx.mock
def test_auth_error_has_actionable_message():
    respx.get("https://example.test/usage").mock(return_value=Response(403, json={"error": "denied"}))
    client = AnalyticsClient("https://example.test/usage", "secret", max_retries=0)
    try:
        list(client.pages(1, 2))
    except AnalyticsAPIError as exc:
        assert "enterprise.analytics.usage.read" in str(exc)
        assert "secret" not in str(exc)
    else:
        raise AssertionError("expected AnalyticsAPIError")

