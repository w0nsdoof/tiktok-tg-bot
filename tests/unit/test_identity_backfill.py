from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.__main__ import backfill_telegram_identities
from bot.services.user_store import UserRecord


@pytest.mark.asyncio
async def test_backfill_observes_resolvable_existing_users() -> None:
    bot = MagicMock()
    resolved_chat = MagicMock(
        username="telegram_user",
        full_name="Telegram User",
    )
    bot.get_chat = AsyncMock(side_effect=[resolved_chat, RuntimeError("chat not found")])
    user_store = MagicMock()
    user_store.list_users = AsyncMock(
        return_value=[UserRecord(user_id=1), UserRecord(user_id=2)]
    )

    await backfill_telegram_identities(bot, user_store)

    assert bot.get_chat.await_count == 2
    user_store.observe_identity.assert_called_once_with(
        1,
        username="telegram_user",
        display_name="Telegram User",
    )


@pytest.mark.asyncio
async def test_backfill_ignores_resolved_chat_without_display_name() -> None:
    bot = MagicMock()
    bot.get_chat = AsyncMock(
        return_value=MagicMock(username="telegram_user", full_name=None)
    )
    user_store = MagicMock()
    user_store.list_users = AsyncMock(return_value=[UserRecord(user_id=1)])

    await backfill_telegram_identities(bot, user_store)

    user_store.observe_identity.assert_not_called()
