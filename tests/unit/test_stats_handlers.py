"""Tests for /stats and /top handlers (mocked service, no Postgres)."""

from unittest.mock import AsyncMock, MagicMock

from bot.handlers.stats import handle_stats, handle_top
from bot.services.stats import GlobalStats, UserStats, TagVideo

PERSONAL = UserStats(
    requests=10,
    downloads=8,
    first_use=None,
    platforms=[("tiktok", 6)],
    creators=[("@cat", 3)],
    hashtags=[("fyp", 4)],
)
GLOBAL = GlobalStats(
    users=3,
    requests=20,
    downloads=15,
    top_users=[(42, 9)],
    platforms=[("tiktok", 12)],
    creators=[("@cat", 5)],
    hashtags=[("fyp", 7)],
)


def _update(user_id=1, lang="en"):
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.language_code = lang
    update.effective_message.reply_text = AsyncMock()
    return update


def _context(stats, is_admin=False, args=None):
    context = MagicMock()
    context.args = args or []
    user_store = MagicMock()
    user_store.is_admin.return_value = is_admin
    context.bot_data = {"stats": stats, "user_store": user_store}
    return context


def _reply_text(update) -> str:
    return update.effective_message.reply_text.await_args.args[0]


class TestStats:
    async def test_disabled_replies_unavailable(self):
        stats = MagicMock()
        stats.enabled = False
        update = _update()
        await handle_stats(update, _context(stats))
        assert "unavailable" in _reply_text(update).lower()
        stats.user_stats.assert_not_called()

    async def test_personal_stats(self):
        stats = MagicMock()
        stats.enabled = True
        stats.user_stats = AsyncMock(return_value=PERSONAL)
        update = _update(user_id=42)
        await handle_stats(update, _context(stats))
        stats.user_stats.assert_awaited_once_with(42)
        text = _reply_text(update)
        assert "10" in text and "@cat" in text and "#fyp" not in text

    async def test_empty_personal_stats(self):
        stats = MagicMock()
        stats.enabled = True
        empty = UserStats(0, 0, None, [], [], [])
        stats.user_stats = AsyncMock(return_value=empty)
        update = _update()
        await handle_stats(update, _context(stats))
        assert "No downloads" in _reply_text(update)

    async def test_all_as_admin_gets_global(self):
        stats = MagicMock()
        stats.enabled = True
        stats.global_stats = AsyncMock(return_value=GLOBAL)
        update = _update()
        await handle_stats(update, _context(stats, is_admin=True, args=["all"]))
        stats.global_stats.assert_awaited_once()
        assert "Global" in _reply_text(update)

    async def test_all_as_non_admin_gets_personal(self):
        stats = MagicMock()
        stats.enabled = True
        stats.user_stats = AsyncMock(return_value=PERSONAL)
        update = _update()
        await handle_stats(update, _context(stats, is_admin=False, args=["all"]))
        stats.user_stats.assert_awaited_once()

    async def test_query_failure_replies_unavailable(self):
        stats = MagicMock()
        stats.enabled = True
        stats.user_stats = AsyncMock(side_effect=RuntimeError("db down"))
        update = _update()
        await handle_stats(update, _context(stats))
        assert "unavailable" in _reply_text(update).lower()


class TestTop:
    async def test_bare_shows_usage(self):
        stats = MagicMock()
        stats.enabled = True
        update = _update()
        await handle_top(update, _context(stats))
        assert "/top tags" in _reply_text(update)

    async def test_junk_shows_usage(self):
        stats = MagicMock()
        stats.enabled = True
        update = _update()
        await handle_top(update, _context(stats, args=["bananas"]))
        assert "/top tags" in _reply_text(update)

    async def test_tags(self):
        stats = MagicMock()
        stats.enabled = True
        stats.top_tags = AsyncMock(return_value=[("fyp", 9)])
        update = _update()
        await handle_top(update, _context(stats, args=["tags"]))
        stats.top_tags.assert_awaited_once_with(10)
        assert "#fyp — 9" in _reply_text(update)

    async def test_creators(self):
        stats = MagicMock()
        stats.enabled = True
        stats.top_creators = AsyncMock(return_value=[("@cat", 5)])
        update = _update()
        await handle_top(update, _context(stats, args=["creators"]))
        assert "@cat — 5" in _reply_text(update)

    async def test_hashtag_lowercases_and_strips_hash(self):
        stats = MagicMock()
        stats.enabled = True
        video = TagVideo(title="Cat", creator="@cat", like_count=100, url="https://t/1")
        stats.top_videos_for_tag = AsyncMock(return_value=[video])
        update = _update()
        await handle_top(update, _context(stats, args=["#FYP"]))
        stats.top_videos_for_tag.assert_awaited_once_with("fyp", 5)
        text = _reply_text(update)
        assert "Cat" in text and "https://t/1" in text

    async def test_unknown_tag_replies_no_data(self):
        stats = MagicMock()
        stats.enabled = True
        stats.top_videos_for_tag = AsyncMock(return_value=[])
        update = _update()
        await handle_top(update, _context(stats, args=["#nosuchtag"]))
        assert "No data" in _reply_text(update)

    async def test_disabled_replies_unavailable(self):
        stats = MagicMock()
        stats.enabled = False
        update = _update()
        await handle_top(update, _context(stats, args=["tags"]))
        assert "unavailable" in _reply_text(update).lower()

    async def test_query_failure_replies_unavailable(self):
        stats = MagicMock()
        stats.enabled = True
        stats.top_tags = AsyncMock(side_effect=RuntimeError("db down"))
        update = _update()
        await handle_top(update, _context(stats, args=["tags"]))
        assert "unavailable" in _reply_text(update).lower()
