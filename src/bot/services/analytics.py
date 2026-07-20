import asyncio
from dataclasses import dataclass
from typing import Any

import asyncpg
import structlog

from bot.models.video_info import VideoInfo

log = structlog.get_logger()

_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS videos (
    platform        text        NOT NULL,
    video_id        text        NOT NULL,
    url             text        NOT NULL,
    title           text,
    description     text,
    hashtags        text[]      NOT NULL DEFAULT '{}',
    author_handle   text,
    author_name     text,
    duration_s      integer,
    view_count      bigint,
    like_count      bigint,
    comment_count   bigint,
    share_count     bigint,
    save_count      bigint,
    track           text,
    artist          text,
    uploaded_at     timestamptz,
    first_seen_at   timestamptz NOT NULL DEFAULT now(),
    last_seen_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (platform, video_id)
);

CREATE TABLE IF NOT EXISTS download_events (
    id              bigserial   PRIMARY KEY,
    ts              timestamptz NOT NULL DEFAULT now(),
    user_id         bigint      NOT NULL,
    chat_type       text        NOT NULL,
    platform        text        NOT NULL,
    video_id        text,
    url             text        NOT NULL,
    output_format   text        NOT NULL,
    status          text        NOT NULL,
    duration_ms     integer,
    file_size_bytes bigint
);

CREATE INDEX IF NOT EXISTS idx_events_ts ON download_events (ts);
CREATE INDEX IF NOT EXISTS idx_events_user ON download_events (user_id);
"""

_UPSERT_VIDEO = """
INSERT INTO videos (
    platform, video_id, url, title, description, hashtags,
    author_handle, author_name, duration_s,
    view_count, like_count, comment_count, share_count, save_count,
    track, artist, uploaded_at
) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
ON CONFLICT (platform, video_id) DO UPDATE SET
    url = EXCLUDED.url,
    title = EXCLUDED.title,
    description = EXCLUDED.description,
    hashtags = EXCLUDED.hashtags,
    author_handle = EXCLUDED.author_handle,
    author_name = EXCLUDED.author_name,
    duration_s = EXCLUDED.duration_s,
    view_count = EXCLUDED.view_count,
    like_count = EXCLUDED.like_count,
    comment_count = EXCLUDED.comment_count,
    share_count = EXCLUDED.share_count,
    save_count = EXCLUDED.save_count,
    track = EXCLUDED.track,
    artist = EXCLUDED.artist,
    uploaded_at = EXCLUDED.uploaded_at,
    last_seen_at = now()
"""

_INSERT_EVENT = """
INSERT INTO download_events (
    user_id, chat_type, platform, video_id, url,
    output_format, status, duration_ms, file_size_bytes
) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
"""


@dataclass
class DownloadEvent:
    user_id: int
    chat_type: str
    platform: str
    url: str
    output_format: str
    status: str
    video_id: str | None = None
    duration_ms: int | None = None
    file_size_bytes: int | None = None


class Analytics:
    """Fire-and-forget event recorder. No-op when dsn is None; never raises."""

    def __init__(self, dsn: str | None) -> None:
        self._dsn = dsn
        self._pool: Any = None
        self._pool_lock: asyncio.Lock = asyncio.Lock()
        self._tasks: set[asyncio.Task[None]] = set()

    @property
    def enabled(self) -> bool:
        return self._dsn is not None

    async def _get_pool(self) -> Any:
        if self._pool is None:
            async with self._pool_lock:
                if self._pool is None:
                    self._pool = await asyncpg.create_pool(self._dsn, min_size=0, max_size=2)
        return self._pool

    async def ensure_schema(self) -> None:
        if not self.enabled:
            return
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                await conn.execute(_SCHEMA_DDL)
            log.info("analytics.schema_ready")
        except Exception:
            log.warning("analytics.schema_failed", exc_info=True)

    def record(self, event: DownloadEvent, video: VideoInfo | None) -> None:
        if not self.enabled:
            return
        task = asyncio.create_task(self._write(event, video))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _write(self, event: DownloadEvent, video: VideoInfo | None) -> None:
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                if video is not None:
                    await conn.execute(
                        _UPSERT_VIDEO,
                        video.platform,
                        video.video_id,
                        video.url,
                        video.title,
                        video.description,
                        video.hashtags,
                        video.author_handle,
                        video.author_name,
                        video.duration_s,
                        video.view_count,
                        video.like_count,
                        video.comment_count,
                        video.share_count,
                        video.save_count,
                        video.track,
                        video.artist,
                        video.uploaded_at,
                    )
                await conn.execute(
                    _INSERT_EVENT,
                    event.user_id,
                    event.chat_type,
                    event.platform,
                    event.video_id,
                    event.url,
                    event.output_format,
                    event.status,
                    event.duration_ms,
                    event.file_size_bytes,
                )
        except Exception:
            log.warning("analytics.write_failed", status=event.status, exc_info=True)

    async def close(self) -> None:
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        if self._pool is not None:
            await self._pool.close()
