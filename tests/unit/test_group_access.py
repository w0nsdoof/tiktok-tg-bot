from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.handlers.group import handle_group_message
from bot.models.request import Platform

URL = "https://www.tiktok.com/@user/video/123"


def _update() -> MagicMock:
    update = MagicMock()
    update.effective_message.text = URL
    update.effective_message.message_id = 10
    update.effective_message.chat_id = -100
    update.effective_user.id = 42
    update.effective_user.language_code = "en"
    return update


def _context(mode: str, *, allowed: bool = False) -> MagicMock:
    context = MagicMock()
    store = MagicMock()
    store.get_runtime.return_value = mode
    store.is_allowed.return_value = allowed
    context.bot_data = {"user_store": store}
    return context


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "allowed", "expected_calls"),
    [
        ("disabled", False, 0),
        ("allowed_users", False, 0),
        ("allowed_users", True, 1),
        ("open", False, 1),
    ],
)
async def test_group_access_policy(mode: str, allowed: bool, expected_calls: int) -> None:
    process = AsyncMock()
    with (
        patch("bot.handlers.group.extract_url", return_value=(URL, Platform.TIKTOK)),
        patch("bot.handlers.group.process_request", process),
    ):
        await handle_group_message(_update(), _context(mode, allowed=allowed))

    assert process.await_count == expected_calls
