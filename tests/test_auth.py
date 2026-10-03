import importlib
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.auth import allowed_email

GOOGLE_ENV = {
    "AUTH_MODE": "google",
    "GOOGLE_CLIENT_ID": "client-id",
    "GOOGLE_CLIENT_SECRET": "client-secret",
    "SESSION_SECRET": "session-secret",
    "AUTH_ALLOWED_DOMAINS": "haw.co.jp, chaintope.com",
}


@pytest.fixture
def google_app(tmp_path, monkeypatch):
    """A fresh app module with Google login enabled (the module wires auth at import time)."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for key, value in GOOGLE_ENV.items():
        monkeypatch.setenv(key, value)
    import app.web as web

    module = importlib.reload(web)
    yield module
    for key in GOOGLE_ENV:
        monkeypatch.setenv(key, "none" if key == "AUTH_MODE" else "")
    importlib.reload(web)  # back to AUTH_MODE=none for the other tests


def test_allowed_email_checks_the_domain_only():
    domains = ("haw.co.jp",)
    assert allowed_email("taro@haw.co.jp", domains)
    assert allowed_email("Taro@HAW.CO.JP", domains)
    assert not allowed_email("taro@gmail.com", domains)
    assert not allowed_email("haw.co.jp", domains)
    assert not allowed_email(None, domains)


def test_without_login_mode_everything_is_open_and_me_is_anonymous(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.web import app

    client = TestClient(app)
    assert client.get("/api/dashboard").status_code == 200
    assert client.get("/api/me").json() == {"auth": "none", "user": None, "domains": []}


def test_oauth_error_returns_to_the_login_page(google_app, monkeypatch):
    from authlib.integrations.base_client.errors import OAuthError

    client = TestClient(google_app.app, follow_redirects=False)
    monkeypatch.setattr(google_app.oauth.google, "authorize_access_token", AsyncMock(side_effect=OAuthError(error="mismatching_state")))
    response = client.get("/auth/callback?code=x&state=bad")
    assert response.status_code == 302 and response.headers["location"] == "/login?error=oauth&detail=mismatching_state"


def test_google_mode_requires_login(google_app):
    client = TestClient(google_app.app, follow_redirects=False)
    assert client.get("/health").status_code == 200
    page = client.get("/insights")
    assert page.status_code == 302 and page.headers["location"] == "/login"  # the React app's login page
    assert client.get("/api/dashboard").status_code == 401
    docs = client.get("/api/docs")
    assert docs.status_code == 302 and docs.headers["location"] == "/login"  # docs are a page: send people to login
    assert client.get("/api/me").json() == {"auth": "google", "user": None, "domains": ["haw.co.jp", "chaintope.com"]}


def test_google_mode_config_validation(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "google")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "x")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "")  # empty, not unset: an unset var would be refilled from .env
    monkeypatch.setenv("SESSION_SECRET", "")
    monkeypatch.setenv("AUTH_ALLOWED_DOMAINS", "")
    from app.config import Settings

    with pytest.raises(ValueError, match="GOOGLE_CLIENT_SECRET, SESSION_SECRET"):
        Settings.from_env()
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "y")
    monkeypatch.setenv("SESSION_SECRET", "z")
    with pytest.raises(ValueError, match="AUTH_ALLOWED_DOMAINS"):
        Settings.from_env()


def test_callback_accepts_company_account_and_rejects_others(google_app, monkeypatch):
    client = TestClient(google_app.app, follow_redirects=False)
    assert client.get("/insights").status_code == 302  # remembers where to go after login

    monkeypatch.setattr(google_app.oauth.google, "authorize_access_token", AsyncMock(return_value={
        "userinfo": {"email": "someone@gmail.com", "email_verified": True, "name": "Someone"},
    }))
    denied = client.get("/auth/callback?code=x&state=y")
    assert denied.status_code == 302 and denied.headers["location"] == "/login?error=domain&email=someone%40gmail.com"
    assert client.get("/api/me").json()["user"] is None

    monkeypatch.setattr(google_app.oauth.google, "authorize_access_token", AsyncMock(return_value={
        "userinfo": {"email": "taro@haw.co.jp", "email_verified": True, "name": "Taro", "picture": "p"},
    }))
    assert client.get("/insights").status_code == 302
    ok = client.get("/auth/callback?code=x&state=y")
    assert ok.status_code == 302 and ok.headers["location"] == "/insights"
    assert client.get("/api/me").json()["user"] == {"email": "taro@haw.co.jp", "name": "Taro", "picture": "p"}
    assert client.get("/api/dashboard").status_code == 200
    assert client.get("/api/docs").status_code == 200

    out = client.get("/logout")
    assert out.status_code == 302 and out.headers["location"] == "/login?logged_out=1"
    assert client.get("/api/dashboard").status_code == 401
    assert client.get("/api/me").json()["user"] is None


def test_login_redirects_to_google_with_hosted_domain(google_app, monkeypatch):
    monkeypatch.setenv("AUTH_ALLOWED_DOMAINS", "haw.co.jp")
    module = importlib.reload(google_app)
    client = TestClient(module.app, follow_redirects=False)
    monkeypatch.setattr(module.oauth.google, "authorize_redirect",
                        AsyncMock(side_effect=lambda request, redirect_uri, **kw: __import__("fastapi").responses.RedirectResponse(
                            f"https://accounts.google.com/o/oauth2/auth?redirect_uri={redirect_uri}&hd={kw.get('hd', '')}&prompt={kw.get('prompt', '')}", status_code=302)))
    response = client.get("/login/google")
    assert response.status_code == 302
    assert "hd=haw.co.jp" in response.headers["location"]
    assert "prompt=select_account" in response.headers["location"]
    assert "redirect_uri=http://testserver/auth/callback" in response.headers["location"]
    # Behind CloudFront the public host arrives in X-Forwarded-Host (set by the viewer-request function).
    forwarded = client.get("/login/google", headers={"x-forwarded-host": "dashboard.example.com", "x-forwarded-proto": "https"})
    assert "redirect_uri=https://dashboard.example.com/auth/callback" in forwarded.headers["location"]


def test_origin_secret_rejects_requests_that_bypass_the_cdn(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ORIGIN_VERIFY_SECRET", "cdn-secret")
    import app.web as web

    module = importlib.reload(web)
    try:
        client = TestClient(module.app)
        assert client.get("/health").status_code == 200  # the container's own health check has no header
        assert client.get("/api/dashboard").status_code == 403
        assert client.get("/api/me", headers={"x-origin-verify": "wrong"}).status_code == 403
        assert client.get("/api/dashboard", headers={"x-origin-verify": "cdn-secret"}).status_code == 200
    finally:
        monkeypatch.setenv("ORIGIN_VERIFY_SECRET", "")
        importlib.reload(web)
