"""Google OpenID Connect login (AUTH_MODE=google).

Follows the in-house pattern (TARO, KEN): sign in with a Google Workspace
account, allow only the company domains. Authlib does the OIDC discovery,
the authorization-code exchange and the ID-token verification; the signed
session cookie holds the user afterwards. With AUTH_MODE=none (local
development) nothing here is installed and every route stays open.
"""
from __future__ import annotations

from typing import Any

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.config import Settings

GOOGLE_DISCOVERY = "https://accounts.google.com/.well-known/openid-configuration"
PUBLIC_PATHS = {"/health", "/login", "/auth/callback", "/logout", "/api/me"}
SESSION_USER = "user"


LOGGED_OUT_PAGE = """<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ログアウトしました</title><link rel="stylesheet" href="/static/styles.css"></head>
<body><main style="max-width:480px;margin:12vh auto;text-align:center"><p class="eyebrow">SIGNED OUT</p><h1 style="font-size:1.6rem">ログアウトしました</h1>
<p class="muted">このダッシュボードのセッションを終了しました。Google アカウント自体からはログアウトしていません。</p>
<p><a href="/login" class="reset-range" style="display:inline-block;padding:10px 18px;text-decoration:none">別のアカウントでログイン</a></p></main></body></html>"""


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
            return {"auth": "none", "user": None}
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
            raise HTTPException(status_code=400, detail=f"ログインに失敗しました: {exc.error}") from exc
        info = token.get("userinfo") or {}
        email = info.get("email")
        if not info.get("email_verified", True) or not allowed_email(email, domains):
            request.session.clear()
            raise HTTPException(status_code=403, detail=f"{email or '不明なアカウント'} は許可されたドメインではありません")
        request.session[SESSION_USER] = {"email": email, "name": info.get("name") or email, "picture": info.get("picture")}
        destination = request.session.pop("next", "/") or "/"
        return RedirectResponse(destination if destination.startswith("/") else "/", status_code=302)

    @app.get("/logout", include_in_schema=False)
    def logout(request: Request):
        # Stop here instead of bouncing to /login, which would silently sign the same Google account back in.
        request.session.clear()
        return HTMLResponse(LOGGED_OUT_PAGE)

    @app.get("/api/me")
    def me(request: Request) -> dict:
        return {"auth": "google", "user": current_user(request)}

    # Middleware order: the session must be decoded before RequireLogin reads it, so add RequireLogin first.
    app.add_middleware(RequireLogin)
    app.add_middleware(
        SessionMiddleware, secret_key=settings.session_secret, session_cookie="dashboard_session",
        https_only=settings.base_url.startswith("https://") if settings.base_url else False,
        same_site="lax", max_age=12 * 60 * 60,
    )
    return oauth
