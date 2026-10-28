from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import User
from telegram.constants import ParseMode

from bot.handlers.admin import handle_request_access_callback


def _update(username: str | None) -> MagicMock:
    update = MagicMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    update.callback_query.from_user = User(
        id=6637911633,
        first_name="BR<100>",
        is_bot=False,
        username=username,
        language_code="en",
    )
    return update


def _context() -> MagicMock:
    context = MagicMock()
    store = MagicMock()
    store.is_allowed.return_value = False
    store.has_pending_request.return_value = False
    store.add_pending_request = AsyncMock(return_value=True)
    store.get_admin_ids.return_value = [1]
    context.bot_data = {"user_store": store}
    context.bot.send_message = AsyncMock()
    return context


@pytest.mark.asyncio
async def test_admin_notice_links_to_user_without_username() -> None:
    context = _context()
    await handle_request_access_callback(_update(None), context)

    kwargs = context.bot.send_message.await_args.kwargs
    assert kwargs["parse_mode"] == ParseMode.HTML
    assert '<a href="tg://user?id=6637911633">BR&lt;100&gt;</a>' in kwargs["text"]
    assert "@none" not in kwargs["text"]


@pytest.mark.asyncio
async def test_admin_notice_shows_username() -> None:
    context = _context()
    await handle_request_access_callback(_update("br100"), context)

    assert "Username: @br100" in context.bot.send_message.await_args.kwargs["text"]
