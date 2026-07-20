"""Tests for the fire-and-forget Analytics service."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.models.video_info import VideoInfo
from bot.services.analytics import Analytics, DownloadEvent

EVENT = DownloadEvent(
    user_id=1,
    chat_type="private",
    platform="tiktok",
    url="https://www.tiktok.com/@u/video/1",
    output_format="default",
    status="ok",
    video_id="1",
    duration_ms=100,
    file_size_bytes=1000,
)
VIDEO = VideoInfo(platform="tiktok", video_id="1", url="https://www.tiktok.com/@u/video/1")


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

    async def close(self):
        pass


class TestDisabled:
    def test_disabled_when_no_dsn(self):
        assert Analytics(None).enabled is False

    @pytest.mark.asyncio
    async def test_record_and_schema_are_noops(self):
        analytics = Analytics(None)
        await analytics.ensure_schema()  # must not attempt any connection
        analytics.record(EVENT, VIDEO)  # must not spawn a task
        assert not analytics._tasks
        await analytics.close()


class TestWrites:
    @pytest.mark.asyncio
    async def test_records_video_upsert_and_event_insert(self):
        analytics = Analytics("postgresql://ignored")
        conn = AsyncMock()
        analytics._pool = _FakePool(conn)

        analytics.record(EVENT, VIDEO)
        await analytics.close()  # awaits pending write tasks

        assert conn.execute.await_count == 2  # upsert videos + insert event

    @pytest.mark.asyncio
    async def test_event_without_video_skips_upsert(self):
        analytics = Analytics("postgresql://ignored")
        conn = AsyncMock()
        analytics._pool = _FakePool(conn)

        analytics.record(EVENT, None)
        await analytics.close()

        assert conn.execute.await_count == 1

    @pytest.mark.asyncio
    async def test_db_failure_is_swallowed(self):
        analytics = Analytics("postgresql://ignored")
        conn = AsyncMock()
        conn.execute.side_effect = RuntimeError("db down")
        analytics._pool = _FakePool(conn)

        analytics.record(EVENT, VIDEO)
        await analytics.close()  # must not raise


class TestPoolRaceCondition:
    @pytest.mark.asyncio
    async def test_concurrent_get_pool_creates_only_once(self):
        """Verify pool creation is guarded by lock — no orphaned pools."""
        analytics = Analytics("postgresql://ignored")

        async def mock_create_pool_with_interleave(*args: object, **kwargs: object) -> MagicMock:
            await asyncio.sleep(0)  # force task interleaving
            return MagicMock()

        with patch(
            "bot.services.analytics.asyncpg.create_pool", new_callable=AsyncMock
        ) as mock_create:
            mock_create.side_effect = mock_create_pool_with_interleave

            pool1, pool2 = await asyncio.gather(analytics._get_pool(), analytics._get_pool())

            assert mock_create.await_count == 1
            assert pool1 is pool2
