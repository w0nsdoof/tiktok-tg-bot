import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, cast
from urllib.parse import urlparse

from authlib.integrations.starlette_client import OAuth
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from bot.config import Settings
from bot.services.analytics import Analytics
from bot.services.stats import StatsService
from bot.services.user_store import AccountAlreadyLinkedError, UserStore

_WEB_DIR = Path(__file__).with_name("web")


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                security_headers = {
                    b"content-security-policy": (
                        b"default-src 'self'; base-uri 'none'; frame-ancestors 'none'; "
                        b"form-action 'self'"
                    ),
                    b"referrer-policy": b"no-referrer",
                    b"x-content-type-options": b"nosniff",
                    b"x-frame-options": b"DENY",
                }
                existing = {key.lower() for key, _ in headers}
                headers.extend(
                    (key, value)
                    for key, value in security_headers.items()
                    if key not in existing
                )
            await send(message)

        await self.app(scope, receive, send_with_headers)


def _safe_next(value: str | None) -> str:
    if not value:
        return "/"
    parsed = urlparse(value)
    return value if not parsed.scheme and not parsed.netloc and value.startswith("/") else "/"


def _groups(user: dict[str, Any]) -> set[str]:
    groups = user.get("groups", [])
    return {str(group) for group in groups} if isinstance(groups, list) else set()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()  # type: ignore[call-arg]
    if not settings.effective_database_dsn:
        raise RuntimeError("DATABASE_DSN or ANALYTICS_DSN is required by the control panel")
    if not settings.web_session_secret:
        raise RuntimeError("WEB_SESSION_SECRET is required by the control panel")
    if not all(
        (settings.control_panel_url, settings.authentik_issuer, settings.authentik_client_id,
         settings.authentik_client_secret)
    ):
        raise RuntimeError("CONTROL_PANEL_URL and Authentik OIDC settings are required")
    assert settings.control_panel_url is not None
    assert settings.authentik_issuer is not None
    assert settings.authentik_client_id is not None
    assert settings.authentik_client_secret is not None
    control_panel_url = settings.control_panel_url
    authentik_issuer = settings.authentik_issuer
    authentik_client_id = settings.authentik_client_id
    authentik_client_secret = settings.authentik_client_secret

    store = UserStore(
        data_dir=settings.data_dir,
        seed_admin_ids=settings.admin_user_ids,
        seed_user_ids=settings.allowed_user_ids,
        dsn=settings.effective_database_dsn,
        runtime_defaults={
            "max_duration": str(settings.max_duration),
            "max_file_size": str(settings.max_file_size),
            "group_access_mode": "open",
        },
    )
    analytics = Analytics(settings.effective_database_dsn)
    stats = StatsService(analytics)

    oauth = OAuth()
    oauth.register(
        name="authentik",
        client_id=authentik_client_id,
        client_secret=authentik_client_secret.get_secret_value(),
        server_metadata_url=(
            f"{authentik_issuer.rstrip('/')}/.well-known/openid-configuration"
        ),
        client_kwargs={"scope": "openid profile email", "code_challenge_method": "S256"},
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await store.initialize()
        await analytics.ensure_schema()
        yield
        await analytics.close()
        await store.close()

    app = FastAPI(
        title="TikTok Telegram Bot Control Panel",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.web_session_secret.get_secret_value(),
        same_site="lax",
        https_only=True,
        max_age=settings.web_session_max_age,
    )
    app.mount("/static", StaticFiles(directory=_WEB_DIR / "static"), name="static")
    templates = Jinja2Templates(directory=_WEB_DIR / "templates")
    app.state.store = store
    app.state.analytics = analytics
    app.state.settings = settings

    def current_user(request: Request) -> dict[str, Any]:
        user = request.session.get("user")
        if not isinstance(user, dict):
            next_url = _safe_next(request.url.path)
            raise HTTPException(303, headers={"Location": f"/login?next={next_url}"})
        return user

    def operator_user(
        user: Annotated[dict[str, Any], Depends(current_user)],
    ) -> dict[str, Any]:
        allowed_groups = {
            settings.authentik_operator_group,
            settings.authentik_admin_group,
        }
        if not _groups(user) & allowed_groups:
            raise HTTPException(403, "Your Authentik account cannot manage this application")
        return user

    def admin_user(
        user: Annotated[dict[str, Any], Depends(operator_user)],
    ) -> dict[str, Any]:
        if settings.authentik_admin_group not in _groups(user):
            raise HTTPException(403, "This action requires the Authentik admin group")
        return user

    def page_context(request: Request, user: dict[str, Any], **values: Any) -> dict[str, Any]:
        csrf_token = request.session.setdefault("csrf_token", secrets.token_urlsafe(24))
        return {"request": request, "user": user, "csrf_token": csrf_token, **values}

    def verify_csrf(request: Request, csrf_token: str) -> None:
        expected = request.session.get("csrf_token")
        if not isinstance(expected, str) or not secrets.compare_digest(expected, csrf_token):
            raise HTTPException(403, "Invalid CSRF token")

    def actor(user: dict[str, Any]) -> str:
        return f"authentik:{user.get('sub', 'unknown')}"

    @app.get("/healthz")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/login")
    async def login(request: Request, next: str | None = None) -> RedirectResponse:
        request.session["login_next"] = _safe_next(next)
        redirect_uri = f"{control_panel_url.rstrip('/')}/auth/callback"
        client = oauth.create_client("authentik")
        assert client is not None
        response = await client.authorize_redirect(request, redirect_uri)
        return cast(RedirectResponse, response)

    @app.get("/auth/callback")
    async def auth_callback(request: Request) -> RedirectResponse:
        client = oauth.create_client("authentik")
        assert client is not None
        token = await client.authorize_access_token(request)
        info = token.get("userinfo")
        if not isinstance(info, dict) or not info.get("sub"):
            raise HTTPException(401, "Authentik did not return an identity")
        request.session["user"] = {
            "sub": info["sub"],
            "preferred_username": info.get("preferred_username", info.get("name", "unknown")),
            "name": info.get("name"),
            "email": info.get("email"),
            "groups": info.get("groups", []),
        }
        return RedirectResponse(request.session.pop("login_next", "/"), status_code=303)

    @app.get("/logout")
    async def logout(request: Request) -> RedirectResponse:
        request.session.clear()
        return RedirectResponse("/login", status_code=303)

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(
        request: Request,
        user: Annotated[dict[str, Any], Depends(operator_user)],
    ) -> HTMLResponse:
        users = await store.list_users()
        global_stats = await stats.global_stats()
        counts = {
            "active": sum(item.status == "active" for item in users),
            "pending": sum(item.status == "pending" for item in users),
            "linked": sum(item.authentik_sub is not None for item in users),
            "admins": sum(item.status == "active" and item.role == "admin" for item in users),
            "requests": global_stats.requests,
            "downloads": global_stats.downloads,
        }
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            page_context(request, user, counts=counts, stats=global_stats),
        )

    @app.get("/users", response_class=HTMLResponse)
    async def users_page(
        request: Request,
        user: Annotated[dict[str, Any], Depends(operator_user)],
    ) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "users.html",
            page_context(
                request,
                user,
                users=await store.list_users(),
                is_admin=settings.authentik_admin_group in _groups(user),
            ),
        )

    @app.post("/users/{telegram_user_id}/status")
    async def change_status(
        request: Request,
        telegram_user_id: int,
        status: Annotated[str, Form()],
        csrf_token: Annotated[str, Form()],
        user: Annotated[dict[str, Any], Depends(operator_user)],
    ) -> RedirectResponse:
        verify_csrf(request, csrf_token)
        if status == "active":
            await store.add_user(telegram_user_id, actor=actor(user))
        elif status == "denied":
            await store.deny_user(telegram_user_id, actor=actor(user))
        elif status == "disabled":
            await store.disable_user(telegram_user_id, actor=actor(user))
        else:
            raise HTTPException(400, "Invalid status")
        return RedirectResponse("/users", status_code=303)

    @app.post("/users/{telegram_user_id}/role")
    async def change_role(
        request: Request,
        telegram_user_id: int,
        role: Annotated[str, Form()],
        csrf_token: Annotated[str, Form()],
        user: Annotated[dict[str, Any], Depends(admin_user)],
    ) -> RedirectResponse:
        verify_csrf(request, csrf_token)
        await store.set_role(telegram_user_id, role, actor=actor(user))
        return RedirectResponse("/users", status_code=303)

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page(
        request: Request,
        user: Annotated[dict[str, Any], Depends(operator_user)],
    ) -> HTMLResponse:
        values = {
            "max_duration": store.get_runtime("max_duration", str(settings.max_duration)),
            "max_file_size": store.get_runtime("max_file_size", str(settings.max_file_size)),
            "group_access_mode": store.get_runtime("group_access_mode", "open"),
        }
        return templates.TemplateResponse(
            request,
            "settings.html",
            page_context(
                request,
                user,
                values=values,
                is_admin=settings.authentik_admin_group in _groups(user),
            ),
        )

    @app.post("/settings")
    async def update_settings(
        request: Request,
        max_duration: Annotated[str, Form()],
        max_file_size: Annotated[str, Form()],
        group_access_mode: Annotated[str, Form()],
        csrf_token: Annotated[str, Form()],
        user: Annotated[dict[str, Any], Depends(admin_user)],
    ) -> RedirectResponse:
        verify_csrf(request, csrf_token)
        await store.set_runtime_settings(
            {
                "max_duration": max_duration,
                "max_file_size": max_file_size,
                "group_access_mode": group_access_mode,
            },
            actor=actor(user),
        )
        return RedirectResponse("/settings", status_code=303)

    @app.get("/link/{token}", response_class=HTMLResponse)
    async def link_account(
        request: Request,
        token: str,
        user: Annotated[dict[str, Any], Depends(current_user)],
    ) -> HTMLResponse:
        conflict = False
        try:
            telegram_user_id = await store.consume_link_token(
                token,
                authentik_sub=str(user["sub"]),
                authentik_username=str(user.get("preferred_username", "unknown")),
            )
        except AccountAlreadyLinkedError:
            telegram_user_id = None
            conflict = True
        return templates.TemplateResponse(
            request,
            "link.html",
            page_context(
                request,
                user,
                telegram_user_id=telegram_user_id,
                conflict=conflict,
            ),
        )

    return app
