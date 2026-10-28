from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import ForceReply, User
from telegram.constants import ParseMode

from bot.filters import relay_target
from bot.handlers.admin import (
    handle_access_denied,
    handle_relay_prompt,
    handle_relay_to_user,
)

PENDING_ID = 6637911633
ADMIN_ID = 1


def _context(*, pending: bool = True) -> MagicMock:
    context = MagicMock()
    store = MagicMock()
    store.has_pending_request.return_value = pending
    store.is_admin.side_effect = lambda user_id: user_id == ADMIN_ID
    store.get_admin_ids.return_value = [ADMIN_ID]
    context.bot_data = {"user_store": store}
    context.bot.send_message = AsyncMock()
    return context


def _bot_message(text: str) -> MagicMock:
    message = MagicMock()
    message.text = text
    message.from_user = User(id=999, first_name="bot", is_bot=True)
    return message


def _message_update(user: User, text: str, reply_to: MagicMock | None = None) -> MagicMock:
    update = MagicMock()
    update.effective_user = user
    update.effective_message.text = text
    update.effective_message.reply_to_message = reply_to
    update.effective_message.reply_text = AsyncMock()
    return update


def _admin() -> User:
    return User(id=ADMIN_ID, first_name="Admin", is_bot=False, language_code="en")


def test_relay_target_reads_user_id_from_bot_message() -> None:
    message = MagicMock()
    message.reply_to_message = _bot_message(f"Access request from BR100 ({PENDING_ID}).")
    assert relay_target(message) == PENDING_ID

    message.reply_to_message = _bot_message("Downloaded video (2024)")
    assert relay_target(message) is None

    message.reply_to_message = None
    assert relay_target(message) is None


@pytest.mark.asyncio
async def test_pending_user_text_is_forwarded_to_admins() -> None:
    context = _context()
    user = User(id=PENDING_ID, first_name="BR100", is_bot=False, language_code="en")
    update = _message_update(user, "I'm <Bob>'s friend")

    await handle_access_denied(update, context)

    kwargs = context.bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == ADMIN_ID
    assert kwargs["parse_mode"] == ParseMode.HTML
    assert f'<a href="tg://user?id={PENDING_ID}">BR100</a> ({PENDING_ID})' in kwargs["text"]
    assert "I'm &lt;Bob&gt;'s friend" in kwargs["text"]
    update.effective_message.reply_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_admin_reply_is_delivered_to_pending_user() -> None:
    context = _context()
    reply_to = _bot_message(f"BR100 ({PENDING_ID}):\nI'm Bob's friend")
    update = _message_update(_admin(), "who are you?", reply_to)

    await handle_relay_to_user(update, context)

    kwargs = context.bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == PENDING_ID
    assert "who are you?" in kwargs["text"]


@pytest.mark.asyncio
async def test_admin_reply_to_non_pending_user_is_refused() -> None:
    context = _context(pending=False)
    reply_to = _bot_message(f"BR100 ({PENDING_ID}):\nhi")
    update = _message_update(_admin(), "who are you?", reply_to)

    await handle_relay_to_user(update, context)

    context.bot.send_message.assert_not_awaited()
    update.effective_message.reply_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_ask_button_sends_force_reply_prompt_with_user_id() -> None:
    context = _context()
    update = MagicMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.from_user = _admin()
    update.callback_query.data = f"access:ask:{PENDING_ID}"

    await handle_relay_prompt(update, context)

    kwargs = context.bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == ADMIN_ID
    assert isinstance(kwargs["reply_markup"], ForceReply)
    assert f"({PENDING_ID})" in kwargs["text"]
