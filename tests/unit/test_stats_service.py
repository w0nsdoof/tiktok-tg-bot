"""Tests for the read-side StatsService (fake pool, no Postgres)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

from bot.services.analytics import Analytics
from bot.services.stats import GlobalStats, StatsService, TagVideo, UserStats


class _FakeAcquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class _FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _FakeAcquire(self._conn)


def _service_with(conn) -> StatsService:
    analytics = Analytics("postgresql://ignored")
    analytics._pool = _FakePool(conn)
    return StatsService(analytics)


FIRST_USE = datetime(2026, 7, 20, tzinfo=UTC)


class TestEnabled:
    def test_follows_analytics(self):
        assert StatsService(Analytics(None)).enabled is False
        assert StatsService(Analytics("postgresql://x")).enabled is True


class TestUserStats:
    async def test_assembles_all_sections(self):
        conn = AsyncMock()
        conn.fetch.side_effect = [
            [{"requests": 10, "downloads": 8, "first_use": FIRST_USE}],
            [{"platform": "tiktok", "n": 6}, {"platform": "youtube", "n": 2}],
            [{"name": "@cat", "n": 3}],
            [{"name": "fyp", "n": 4}],
        ]
        stats = await _service_with(conn).user_stats(42)
        assert stats == UserStats(
            requests=10,
            downloads=8,
            first_use=FIRST_USE,
            platforms=[("tiktok", 6), ("youtube", 2)],
            creators=[("@cat", 3)],
            hashtags=[("fyp", 4)],
        )
        assert conn.fetch.await_count == 4

    async def test_empty_user_has_empty_sections(self):
        conn = AsyncMock()
        conn.fetch.side_effect = [
            [{"requests": 0, "downloads": 0, "first_use": None}],
            [],
            [],
            [],
        ]
        stats = await _service_with(conn).user_stats(42)
        assert stats.requests == 0
        assert stats.first_use is None
        assert stats.platforms == []


class TestGlobalStats:
    async def test_assembles_all_sections(self):
        conn = AsyncMock()
        conn.fetch.side_effect = [
            [{"users": 3, "requests": 20, "downloads": 15}],
            [{"user_id": 42, "n": 9}, {"user_id": 7, "n": 6}],
            [{"platform": "tiktok", "n": 12}],
            [{"name": "@cat", "n": 5}],
            [{"name": "fyp", "n": 7}],
        ]
        g = await _service_with(conn).global_stats()
        assert g == GlobalStats(
            users=3,
            requests=20,
            downloads=15,
            top_users=[(42, 9), (7, 6)],
            platforms=[("tiktok", 12)],
            creators=[("@cat", 5)],
            hashtags=[("fyp", 7)],
        )


class TestTops:
    async def test_top_tags(self):
        conn = AsyncMock()
        conn.fetch.return_value = [{"name": "fyp", "n": 9}, {"name": "cat", "n": 4}]
        rows = await _service_with(conn).top_tags(10)
        assert rows == [("fyp", 9), ("cat", 4)]
        assert conn.fetch.await_args.args[-1] == 10  # limit is parameterized

    async def test_top_creators(self):
        conn = AsyncMock()
        conn.fetch.return_value = [{"name": "@cat", "n": 5}]
        assert await _service_with(conn).top_creators(10) == [("@cat", 5)]

    async def test_top_videos_for_tag(self):
        conn = AsyncMock()
        conn.fetch.return_value = [
            {"title": "Cat", "creator": "@cat", "like_count": 100, "url": "https://t/1"},
            {"title": None, "creator": "@dog", "like_count": None, "url": "https://t/2"},
        ]
        videos = await _service_with(conn).top_videos_for_tag("fyp", 5)
        assert videos == [
            TagVideo(title="Cat", creator="@cat", like_count=100, url="https://t/1"),
            TagVideo(title=None, creator="@dog", like_count=None, url="https://t/2"),
        ]
        assert conn.fetch.await_args.args[1] == "fyp"
