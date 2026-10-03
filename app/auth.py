"""Google OpenID Connect login (AUTH_MODE=google).

Follows the in-house pattern (TARO, KEN): sign in with a Google Workspace
account, allow only the company domains. Authlib does the OIDC discovery,
the authorization-code exchange and the ID-token verification; the signed
session cookie holds the user afterwards. With AUTH_MODE=none (local
development) nothing here is installed and every route stays open.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.config import Settings

GOOGLE_DISCOVERY = "https://accounts.google.com/.well-known/openid-configuration"
PUBLIC_PATHS = {"/health", "/login", "/login/google", "/auth/callback", "/logout", "/api/me"}
LOGIN_PAGE = Path(__file__).parent / "static" / "login.html"
SESSION_USER = "user"


def allowed_email(email: str | None, domains: tuple[str, ...]) -> bool:
    if not email or "@" not in email:
        return False
    return email.rsplit("@", 1)[1].lower() in domains


def current_user(request: Request) -> dict[str, Any] | None:
    try:
        return request.session.get(SESSION_USER)
    except AssertionError:  # SessionMiddleware not installed (AUTH_MODE=none)
        return None


class RequireLogin(BaseHTTPMiddleware):
    """Everything except the public paths needs a session; APIs get 401, pages a redirect."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in PUBLIC_PATHS or path.startswith("/static/") or request.session.get(SESSION_USER):
            return await call_next(request)
        if path.startswith("/api/"):
            return JSONResponse({"detail": "ログインが必要です"}, status_code=401)
        request.session["next"] = path
        return RedirectResponse("/login", status_code=302)


def install(app: FastAPI, settings: Settings) -> OAuth | None:
    """Wire the login routes and middleware; returns the OAuth registry for tests to patch."""
    if settings.auth_mode != "google":
        @app.get("/api/me")
        def me_anonymous() -> dict:
            return {"auth": "none", "user": None, "domains": []}
        return None

    oauth = OAuth()
    oauth.register(
        name="google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        server_metadata_url=GOOGLE_DISCOVERY,
        client_kwargs={"scope": "openid email profile"},
    )
    domains = settings.auth_allowed_domains

    @app.get("/login", include_in_schema=False)
    def login_page(request: Request):
        """The sign-in page; already signed-in users go straight to the dashboard."""
        if request.session.get(SESSION_USER):
            return RedirectResponse("/", status_code=302)
        return FileResponse(LOGIN_PAGE)

    @app.get("/login/google", include_in_schema=False)
    async def login(request: Request):
        redirect_uri = str(request.url_for("auth_callback"))
        if settings.base_url:  # behind a proxy the request host may be internal
            redirect_uri = settings.base_url.rstrip("/") + "/auth/callback"
        extra = {"prompt": "select_account"}  # always show the chooser, so logging out really means logging out
        if len(domains) == 1:
            extra["hd"] = domains[0]  # narrow the chooser to the Workspace domain
        return await oauth.google.authorize_redirect(request, redirect_uri, **extra)

    @app.get("/auth/callback", include_in_schema=False, name="auth_callback")
    async def auth_callback(request: Request):
        try:
            token = await oauth.google.authorize_access_token(request)
        except OAuthError as exc:
            return RedirectResponse("/login?" + urlencode({"error": "oauth", "detail": exc.error or ""}), status_code=302)
        info = token.get("userinfo") or {}
        email = info.get("email")
        if not info.get("email_verified", True) or not allowed_email(email, domains):
            request.session.clear()
            return RedirectResponse("/login?" + urlencode({"error": "domain", "email": email or ""}), status_code=302)
        request.session[SESSION_USER] = {"email": email, "name": info.get("name") or email, "picture": info.get("picture")}
        destination = request.session.pop("next", "/") or "/"
        return RedirectResponse(destination if destination.startswith("/") else "/", status_code=302)

    @app.get("/logout", include_in_schema=False)
    def logout(request: Request):
        # The login page does not auto-redirect to Google, so this does not silently sign the same account back in.
        request.session.clear()
        return RedirectResponse("/login?logged_out=1", status_code=302)

    @app.get("/api/me")
    def me(request: Request) -> dict:
        return {"auth": "google", "user": current_user(request), "domains": list(domains)}

    # Middleware order: the session must be decoded before RequireLogin reads it, so add RequireLogin first.
    app.add_middleware(RequireLogin)
    app.add_middleware(
        SessionMiddleware, secret_key=settings.session_secret, session_cookie="dashboard_session",
        https_only=settings.base_url.startswith("https://") if settings.base_url else False,
        same_site="lax", max_age=12 * 60 * 60,
    )
    return oauth
