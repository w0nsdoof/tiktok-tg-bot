from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import SecretStr

from bot.config import Settings
from bot.web import SecurityHeadersMiddleware, _groups, _safe_next, create_app


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "bot_token": SecretStr("test-token"),
        "database_dsn": SecretStr("postgresql://unused"),
        "control_panel_url": "https://bot.example.com",
        "web_session_secret": SecretStr("a-long-test-session-secret"),
        "authentik_issuer": "https://auth.example.com/application/o/tiktok-bot",
        "authentik_client_id": "tiktok-bot",
        "authentik_client_secret": SecretStr("test-client-secret"),
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "/"),
        ("/users", "/users"),
        ("https://attacker.example", "/"),
        ("//attacker.example", "/"),
    ],
)
def test_safe_next_prevents_open_redirects(value: str | None, expected: str) -> None:
    assert _safe_next(value) == expected


def test_group_claims_require_a_list() -> None:
    assert _groups({"groups": ["operators", "admins"]}) == {"operators", "admins"}
    assert _groups({"groups": "admins"}) == set()


def test_control_panel_routes_are_registered() -> None:
    app = create_app(_settings())
    paths = {route.path for route in app.routes}

    assert {"/", "/users", "/settings", "/login", "/auth/callback", "/link/{token}"} <= paths
    assert "/docs" not in paths


def test_control_panel_requires_a_session_secret() -> None:
    with pytest.raises(RuntimeError, match="WEB_SESSION_SECRET"):
        create_app(_settings(web_session_secret=None))


def test_all_control_panel_templates_compile() -> None:
    template_dir = Path(__file__).parents[2] / "src/bot/web/templates"
    environment = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(),
    )

    for template in template_dir.glob("*.html"):
        environment.get_template(template.name)


@pytest.mark.asyncio
async def test_security_middleware_adds_browser_headers() -> None:
    sent: list[dict[str, object]] = []

    async def inner(scope: object, receive: object, send: object) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b""}

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    middleware = SecurityHeadersMiddleware(inner)  # type: ignore[arg-type]
    await middleware({"type": "http", "path": "/"}, receive, send)  # type: ignore[arg-type]

    headers = dict(sent[0]["headers"])  # type: ignore[arg-type]
    assert headers[b"referrer-policy"] == b"no-referrer"
    assert headers[b"x-frame-options"] == b"DENY"
