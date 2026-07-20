# Analytics Data Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record every download request (success and failure) plus normalized video metadata into the shared Postgres, fire-and-forget, so analytics surfaces can be built later.

**Architecture:** A new `VideoInfo` model is populated for free from the yt-dlp info dict that `extract_metadata()` already fetches. A new `Analytics` service owns a small asyncpg pool and writes a `videos` upsert + `download_events` insert in a background task; any DB error is logged and dropped. Both request paths (`process_request()`, `handle_inline_query()`) funnel every exit through exactly one `analytics.record()` call.

**Tech Stack:** Python 3.12, python-telegram-bot 21.x, asyncpg (new), pydantic-settings, structlog, pytest + pytest-asyncio. Postgres 16 (shared container, external `db` Docker network).

**Spec:** `docs/superpowers/specs/2026-07-20-analytics-data-layer-design.md` — source of truth for schema and semantics.

## Global Constraints

- Python `>=3.12`; mypy `strict = true` — all new code fully typed (asyncpg gets an `ignore_missing_imports` override).
- ruff: `select = ["E", "F", "I", "N", "UP", "B", "SIM", "RUF"]`, `line-length = 100`, `target-version = py312`.
- The GitHub repo is **public**: no DSNs, passwords, or hostnames-with-credentials in code, compose, tests, or docs. Secrets live only in server `.env` files.
- Analytics must never slow or break a download: `record()` is synchronous fire-and-forget; every DB failure is `log.warning(...)` + drop. Bot behavior with `ANALYTICS_DSN` unset is byte-identical to today.
- Only new runtime dependency: `asyncpg`. No ORM, no migration framework.
- Run commands from the repo root: `uv sync --extra dev`, `uv run pytest tests/ -v`, `uv run ruff check .`, `uv run mypy`. (CLAUDE.md's `cd src && uv run pytest` variant also works — rootdir resolves to the repo root either way.)
- Commit messages: conventional style (`feat:`, `test:`, `docs:`, `chore:`) matching `git log`.

---

### Task 1: `VideoInfo` model + hashtag extraction

**Files:**
- Create: `src/bot/models/video_info.py`
- Test: `tests/unit/test_video_info.py`

**Interfaces:**
- Consumes: nothing (leaf module; stdlib only).
- Produces: `VideoInfo` dataclass (fields exactly as below), `VideoInfo.from_info_dict(info: dict[str, Any], url: str) -> VideoInfo`, `extract_hashtags(description: str | None, tags: list[str] | None = None) -> list[str]`. Platform is inferred from the info dict's `extractor_key`/`extractor` (values `"tiktok" | "youtube" | "instagram" | "unknown"`), NOT passed in — this avoids touching `extract_metadata()`'s signature.

- [ ] **Step 1: Write the failing tests**

Field mappings come from `docs/research/yt-dlp-metadata.md` (per-platform tables).

```python
"""Tests for VideoInfo normalization from yt-dlp info dicts."""

from datetime import UTC, datetime

from bot.models.video_info import VideoInfo, extract_hashtags


class TestExtractHashtags:
    def test_from_description(self):
        assert extract_hashtags("cool vid #fyp #Dance") == ["dance", "fyp"]

    def test_from_tags_list(self):
        assert extract_hashtags(None, ["Shorts", "gaming"]) == ["gaming", "shorts"]

    def test_merges_and_dedupes(self):
        assert extract_hashtags("#fyp text", ["FYP", "viral"]) == ["fyp", "viral"]

    def test_empty(self):
        assert extract_hashtags(None, None) == []


TIKTOK_INFO = {
    "id": "7300000000000000000",
    "extractor_key": "TikTok",
    "title": "cat does a flip #cat",
    "description": "cat does a flip #cat #fyp",
    "timestamp": 1700000000,
    "duration": 15,
    "view_count": 1000,
    "like_count": 100,
    "comment_count": 10,
    "repost_count": 5,
    "save_count": 7,
    "uploader": "catlover99",
    "channel": "Cat Lover",
    "track": "original sound",
    "artists": ["catlover99"],
}

YOUTUBE_INFO = {
    "id": "BGQWPY4IigY",
    "extractor_key": "Youtube",
    "title": "Epic short",
    "description": "watch this",
    "tags": ["Epic", "shorts"],
    "timestamp": 1700000100,
    "duration": 45,
    "view_count": 5000,
    "like_count": 300,
    "comment_count": 20,
    "uploader": "Some Channel",
    "uploader_id": "@somechannel",
}

INSTAGRAM_INFO = {
    "id": "Cxyz123",
    "extractor_key": "Instagram",
    "title": "Video by someuser",
    "description": "sunset reel #sunset",
    "timestamp": 1700000200,
    "duration": 12.4,
    "like_count": 250,
    "comment_count": 8,
    "uploader": "Some User",
    "channel": "someuser",
}


class TestFromInfoDict:
    def test_tiktok_mapping(self):
        url = "https://www.tiktok.com/@catlover99/video/7300000000000000000"
        v = VideoInfo.from_info_dict(TIKTOK_INFO, url)
        assert v.platform == "tiktok"
        assert v.video_id == "7300000000000000000"
        assert v.author_handle == "catlover99"
        assert v.author_name == "Cat Lover"
        assert v.hashtags == ["cat", "fyp"]
        assert v.share_count == 5
        assert v.save_count == 7
        assert v.track == "original sound"
        assert v.artist == "catlover99"
        assert v.uploaded_at == datetime.fromtimestamp(1700000000, tz=UTC)

    def test_youtube_mapping(self):
        v = VideoInfo.from_info_dict(YOUTUBE_INFO, "https://www.youtube.com/shorts/BGQWPY4IigY")
        assert v.platform == "youtube"
        assert v.author_handle == "@somechannel"
        assert v.author_name == "Some Channel"
        assert v.hashtags == ["epic", "shorts"]
        assert v.share_count is None
        assert v.save_count is None

    def test_instagram_mapping(self):
        v = VideoInfo.from_info_dict(INSTAGRAM_INFO, "https://www.instagram.com/reel/Cxyz123/")
        assert v.platform == "instagram"
        assert v.author_handle == "someuser"
        assert v.author_name == "Some User"
        assert v.duration_s == 12  # float truncated to int
        assert v.view_count is None

    def test_unknown_extractor_and_missing_fields(self):
        v = VideoInfo.from_info_dict({"id": 42, "extractor": "weird"}, "https://x.test/42")
        assert v.platform == "unknown"
        assert v.video_id == "42"  # coerced to str
        assert v.hashtags == []
        assert v.uploaded_at is None
        assert v.duration_s is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_video_info.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.models.video_info'`

- [ ] **Step 3: Write the implementation**

```python
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def extract_hashtags(description: str | None, tags: list[str] | None = None) -> list[str]:
    """Merge hashtags from a tags list (YouTube) and #tag text (TikTok/Instagram)."""
    result: set[str] = set()
    if tags:
        result.update(t.lower() for t in tags)
    if description:
        result.update(t.lower() for t in re.findall(r"#(\w+)", description))
    return sorted(result)


def _platform_from_extractor(info: dict[str, Any]) -> str:
    key = str(info.get("extractor_key") or info.get("extractor") or "").lower()
    for name in ("tiktok", "youtube", "instagram"):
        if name in key:
            return name
    return "unknown"


# platform -> (handle field, display-name field) in the yt-dlp info dict
_AUTHOR_FIELDS: dict[str, tuple[str, str]] = {
    "tiktok": ("uploader", "channel"),
    "youtube": ("uploader_id", "uploader"),
    "instagram": ("channel", "uploader"),
}


@dataclass
class VideoInfo:
    platform: str
    video_id: str
    url: str
    title: str | None = None
    description: str | None = None
    hashtags: list[str] = field(default_factory=list)
    author_handle: str | None = None
    author_name: str | None = None
    duration_s: int | None = None
    view_count: int | None = None
    like_count: int | None = None
    comment_count: int | None = None
    share_count: int | None = None
    save_count: int | None = None
    track: str | None = None
    artist: str | None = None
    uploaded_at: datetime | None = None

    @classmethod
    def from_info_dict(cls, info: dict[str, Any], url: str) -> "VideoInfo":
        platform = _platform_from_extractor(info)
        handle_key, name_key = _AUTHOR_FIELDS.get(platform, ("uploader", "channel"))
        artists = info.get("artists")
        artist = ", ".join(artists) if artists else info.get("artist")
        timestamp = info.get("timestamp")
        duration = info.get("duration")
        return cls(
            platform=platform,
            video_id=str(info.get("id", "")),
            url=url,
            title=info.get("title"),
            description=info.get("description"),
            hashtags=extract_hashtags(info.get("description"), info.get("tags")),
            author_handle=info.get(handle_key),
            author_name=info.get(name_key),
            duration_s=int(duration) if duration is not None else None,
            view_count=info.get("view_count"),
            like_count=info.get("like_count"),
            comment_count=info.get("comment_count"),
            share_count=info.get("repost_count") if platform == "tiktok" else None,
            save_count=info.get("save_count") if platform == "tiktok" else None,
            track=info.get("track"),
            artist=artist,
            uploaded_at=datetime.fromtimestamp(timestamp, tz=UTC) if timestamp else None,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_video_info.py -v`
Expected: all PASS

- [ ] **Step 5: Lint, type-check, commit**

Run: `uv run ruff check . && uv run mypy`
Expected: clean (pre-existing issues, if any, are out of scope — only new files must be clean)

```bash
git add src/bot/models/video_info.py tests/unit/test_video_info.py
git commit -m "feat: add VideoInfo model normalizing yt-dlp metadata"
```

---

### Task 2: Populate `VideoMetadata.info` in the downloader

**Files:**
- Modify: `src/bot/services/downloader.py` (dataclass `VideoMetadata` ~line 38; `_extract_metadata_sync` ~line 107)
- Test: `tests/unit/test_downloader.py` (append a new test class)

**Interfaces:**
- Consumes: `VideoInfo.from_info_dict(info, url)` from Task 1.
- Produces: `VideoMetadata.info: VideoInfo | None` — populated on every successful `extract_metadata()` call; `None` if normalization itself fails (a normalization bug must never break downloads).

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_downloader.py`:

```python
from unittest.mock import MagicMock, patch

from bot.services.downloader import _extract_metadata_sync


class TestMetadataVideoInfo:
    def _fake_ydl(self, info):
        ydl = MagicMock()
        ydl.extract_info.return_value = info
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=ydl)
        cm.__exit__ = MagicMock(return_value=False)
        return cm

    def test_info_populated(self):
        info = {
            "id": "123",
            "extractor_key": "TikTok",
            "title": "t",
            "description": "#fyp",
            "duration": 10,
            "uploader": "u",
            "channel": "U",
        }
        with patch(
            "bot.services.downloader.yt_dlp.YoutubeDL",
            return_value=self._fake_ydl(info),
        ):
            meta = _extract_metadata_sync("https://www.tiktok.com/@u/video/123")
        assert meta.info is not None
        assert meta.info.video_id == "123"
        assert meta.info.platform == "tiktok"
        assert meta.info.hashtags == ["fyp"]

    def test_normalization_failure_returns_none_info(self):
        info = {"id": "123", "extractor_key": "TikTok", "duration": 10}
        with (
            patch(
                "bot.services.downloader.yt_dlp.YoutubeDL",
                return_value=self._fake_ydl(info),
            ),
            patch(
                "bot.services.downloader.VideoInfo.from_info_dict",
                side_effect=RuntimeError("boom"),
            ),
        ):
            meta = _extract_metadata_sync("https://www.tiktok.com/@u/video/123")
        assert meta.info is None
        assert meta.duration == 10  # metadata itself still works
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_downloader.py -v -k VideoInfo`
Expected: FAIL — `VideoMetadata` has no attribute/argument `info` (and no `VideoInfo` import)

- [ ] **Step 3: Implement**

In `src/bot/services/downloader.py`, add the import near the top:

```python
from bot.models.video_info import VideoInfo
```

Extend the dataclass:

```python
@dataclass
class VideoMetadata:
    duration: int | None
    file_size: int | None
    title: str | None
    is_slideshow: bool = False
    info: VideoInfo | None = None
```

In `_extract_metadata_sync`, replace the `return VideoMetadata(...)` block:

```python
            is_slideshow = info.get("vcodec") == "none" and "/photo/" in resolved_url
            video_info: VideoInfo | None = None
            try:
                video_info = VideoInfo.from_info_dict(info, normalized_url)
            except Exception:
                log.warning("metadata.video_info_failed", exc_info=True)
            return VideoMetadata(
                duration=info.get("duration"),
                file_size=info.get("filesize") or info.get("filesize_approx"),
                title=info.get("title"),
                is_slideshow=is_slideshow,
                info=video_info,
            )
```

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest tests/ -v`
Expected: all PASS (existing `VideoMetadata(...)` constructions stay valid — the new field has a default)

- [ ] **Step 5: Lint, type-check, commit**

Run: `uv run ruff check . && uv run mypy`

```bash
git add src/bot/services/downloader.py tests/unit/test_downloader.py
git commit -m "feat: attach normalized VideoInfo to extracted metadata"
```

---

### Task 3: `Analytics` service (asyncpg, fire-and-forget) + config

**Files:**
- Create: `src/bot/services/analytics.py`
- Modify: `pyproject.toml` (add `asyncpg` dependency + mypy override)
- Modify: `src/bot/config.py` (add `analytics_dsn`)
- Test: `tests/unit/test_analytics.py`

**Interfaces:**
- Consumes: `VideoInfo` from Task 1.
- Produces (used by Tasks 4–6):
  - `DownloadEvent(user_id: int, chat_type: str, platform: str, url: str, output_format: str, status: str, video_id: str | None = None, duration_ms: int | None = None, file_size_bytes: int | None = None)`
  - `Analytics(dsn: str | None)` with: `enabled: bool` property, `async ensure_schema() -> None`, `record(event: DownloadEvent, video: VideoInfo | None) -> None` (synchronous, spawns a task), `async close() -> None`.
  - `Settings.analytics_dsn: SecretStr | None` (env `ANALYTICS_DSN`).

- [ ] **Step 1: Add the dependency and config**

In `pyproject.toml` `[project].dependencies` add:

```toml
    "asyncpg>=0.30",
```

At the end of the file add:

```toml
[[tool.mypy.overrides]]
module = "asyncpg.*"
ignore_missing_imports = true
```

In `src/bot/config.py` add after `bot_token`:

```python
    analytics_dsn: SecretStr | None = None
```

Run: `uv sync --extra dev`
Expected: asyncpg installed.

- [ ] **Step 2: Write the failing tests**

```python
"""Tests for the fire-and-forget Analytics service."""

from unittest.mock import AsyncMock

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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_analytics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.services.analytics'`

- [ ] **Step 4: Implement**

`src/bot/services/analytics.py` — DDL and column lists must match the spec exactly:

```python
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
        self._tasks: set[asyncio.Task[None]] = set()

    @property
    def enabled(self) -> bool:
        return self._dsn is not None

    async def _get_pool(self) -> Any:
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_analytics.py -v`
Expected: all PASS

- [ ] **Step 6: Lint, type-check, commit**

Run: `uv run ruff check . && uv run mypy`

```bash
git add src/bot/services/analytics.py tests/unit/test_analytics.py pyproject.toml uv.lock src/bot/config.py
git commit -m "feat: add fire-and-forget Analytics service writing to Postgres"
```

---

### Task 4: Capture point in `process_request()`

**Files:**
- Modify: `src/bot/handlers/common.py` (whole `process_request` body)
- Modify: `tests/unit/test_handler_routing.py` (`_make_context`, `_make_message` helpers)
- Test: Create `tests/unit/test_analytics_capture.py`

**Interfaces:**
- Consumes: `Analytics.record(event, video)`, `DownloadEvent` (Task 3), `VideoMetadata.info` (Task 2). Reads `context.bot_data["analytics"]` — Task 6 wires it; tests inject a `MagicMock()`.
- Produces: every exit of `process_request()` emits exactly one event. Status values: `ok`, `too_long`, `too_large`, `not_slideshow`, any `ErrorType.value`, `unknown_error`. `chat_type` is `"private"` when `message.chat.type == "private"`, else `"group"`. `file_size_bytes` set for video (post-download size) and audio (sent file size); `None` for slideshows.

- [ ] **Step 1: Update existing test helpers**

In `tests/unit/test_handler_routing.py`:

In `_make_context`, add an `analytics` key to `ctx.bot_data`:

```python
    ctx.bot_data = {
        "settings": settings or MagicMock(
            max_duration=300,
            max_file_size=50,
            download_dir="/tmp/test",
        ),
        "queue": MagicMock(),
        "analytics": MagicMock(),
    }
```

In `_make_message`, pin the fields the capture code reads:

```python
    msg = AsyncMock()
    msg.chat_id = 123
    msg.message_id = 456
    msg.chat.type = "private"
    msg.from_user.id = 111
```

Run: `uv run pytest tests/unit/test_handler_routing.py -v`
Expected: all PASS (unchanged behavior so far)

- [ ] **Step 2: Write the failing capture tests**

`tests/unit/test_analytics_capture.py`:

```python
"""One analytics event per process_request() exit path."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.models.request import OutputFormat, Platform
from bot.models.video_info import VideoInfo
from bot.services.downloader import ErrorType, VideoDownloadError, VideoMetadata

VIDEO_URL = "https://www.tiktok.com/@user/video/123"
VIDEO_INFO = VideoInfo(platform="tiktok", video_id="123", url=VIDEO_URL)
VIDEO_METADATA = VideoMetadata(
    duration=30, file_size=1000, title="Test", is_slideshow=False, info=VIDEO_INFO
)


def _make_context():
    ctx = MagicMock()
    ctx.bot_data = {
        "settings": MagicMock(max_duration=300, max_file_size=50, download_dir="/tmp/test"),
        "queue": MagicMock(),
        "analytics": MagicMock(),
    }
    ctx.bot_data["queue"].is_full = False
    ctx.bot_data["queue"].acquire = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(),
            __aexit__=AsyncMock(return_value=False),
        )
    )
    ctx.bot.send_chat_action = AsyncMock()
    return ctx


def _make_message():
    msg = AsyncMock()
    msg.chat_id = 123
    msg.message_id = 456
    msg.chat.type = "private"
    msg.from_user.id = 111
    status_msg = AsyncMock()
    msg.reply_text.return_value = status_msg
    return msg


def _recorded_event(ctx):
    record = ctx.bot_data["analytics"].record
    assert record.call_count == 1
    return record.call_args.args


@pytest.mark.asyncio
async def test_success_records_ok():
    msg, ctx = _make_message(), _make_context()
    with (
        patch("bot.handlers.common.extract_url", return_value=(VIDEO_URL, Platform.TIKTOK)),
        patch("bot.handlers.common.parse_output_format", return_value=OutputFormat.DEFAULT),
        patch("bot.handlers.common.extract_metadata", return_value=VIDEO_METADATA),
        patch("bot.handlers.common.download_video") as mock_dl,
        patch("bot.handlers.common.os.path.getsize", return_value=1000),
        patch("bot.handlers.common.os.path.exists", return_value=False),
        patch("builtins.open", MagicMock()),
    ):
        mock_dl.return_value = "/tmp/test/video.mp4"
        from bot.handlers.common import process_request
        await process_request(msg, VIDEO_URL, "en", ctx)

    event, video = _recorded_event(ctx)
    assert event.status == "ok"
    assert event.platform == "tiktok"
    assert event.chat_type == "private"
    assert event.user_id == 111
    assert event.output_format == "default"
    assert event.video_id == "123"
    assert event.file_size_bytes == 1000
    assert video is VIDEO_INFO


@pytest.mark.asyncio
async def test_too_long_rejection_records_event():
    msg, ctx = _make_message(), _make_context()
    long_meta = VideoMetadata(duration=999, file_size=10, title="t", info=VIDEO_INFO)
    with (
        patch("bot.handlers.common.extract_url", return_value=(VIDEO_URL, Platform.TIKTOK)),
        patch("bot.handlers.common.parse_output_format", return_value=OutputFormat.DEFAULT),
        patch("bot.handlers.common.extract_metadata", return_value=long_meta),
    ):
        from bot.handlers.common import process_request
        await process_request(msg, VIDEO_URL, "en", ctx)

    event, _ = _recorded_event(ctx)
    assert event.status == "too_long"


@pytest.mark.asyncio
async def test_images_on_video_records_not_slideshow():
    msg, ctx = _make_message(), _make_context()
    with (
        patch("bot.handlers.common.extract_url", return_value=(VIDEO_URL, Platform.TIKTOK)),
        patch("bot.handlers.common.parse_output_format", return_value=OutputFormat.IMAGES),
        patch("bot.handlers.common.extract_metadata", return_value=VIDEO_METADATA),
    ):
        from bot.handlers.common import process_request
        await process_request(msg, f"images {VIDEO_URL}", "en", ctx)

    event, _ = _recorded_event(ctx)
    assert event.status == "not_slideshow"


@pytest.mark.asyncio
async def test_download_error_records_error_type():
    msg, ctx = _make_message(), _make_context()
    with (
        patch("bot.handlers.common.extract_url", return_value=(VIDEO_URL, Platform.TIKTOK)),
        patch("bot.handlers.common.parse_output_format", return_value=OutputFormat.DEFAULT),
        patch(
            "bot.handlers.common.extract_metadata",
            side_effect=VideoDownloadError(ErrorType.PRIVATE),
        ),
    ):
        from bot.handlers.common import process_request
        await process_request(msg, VIDEO_URL, "en", ctx)

    event, video = _recorded_event(ctx)
    assert event.status == "private"
    assert event.video_id is None
    assert video is None


@pytest.mark.asyncio
async def test_unhandled_exception_records_unknown_error():
    msg, ctx = _make_message(), _make_context()
    with (
        patch("bot.handlers.common.extract_url", return_value=(VIDEO_URL, Platform.TIKTOK)),
        patch("bot.handlers.common.parse_output_format", return_value=OutputFormat.DEFAULT),
        patch("bot.handlers.common.extract_metadata", side_effect=RuntimeError("boom")),
    ):
        from bot.handlers.common import process_request
        await process_request(msg, VIDEO_URL, "en", ctx)

    event, _ = _recorded_event(ctx)
    assert event.status == "unknown_error"
```

Run: `uv run pytest tests/unit/test_analytics_capture.py -v`
Expected: FAIL — `record` never called (capture code doesn't exist yet)

- [ ] **Step 3: Restructure `process_request()`**

Replace the body of `process_request` in `src/bot/handlers/common.py`. New imports at the top of the file:

```python
import time

from bot.models.video_info import VideoInfo
from bot.services.analytics import Analytics, DownloadEvent
```

The complete final function (`_send_slideshow`, `_cleanup_slideshow`, and the module-level `_ERROR_TYPE_TO_MESSAGE_KEY` stay exactly as they are):

```python
async def process_request(
    message: Message,
    text: str,
    lang: str | None,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    reply_to: int | None = None,
) -> None:
    """Shared request processing for private and group handlers.

    Args:
        message: The incoming Telegram message.
        text: The message text.
        lang: User language code.
        context: Bot context with settings and queue.
        reply_to: Message ID to reply to (used in group chats for threading).
    """
    result = extract_url(text)
    if result is None:
        return None

    url, platform = result
    output_format = parse_output_format(text, url)
    log.info("request.format_detected", output_format=output_format.value)

    settings: Settings = context.bot_data["settings"]
    queue: DownloadQueue = context.bot_data["queue"]
    analytics: Analytics = context.bot_data["analytics"]

    if queue.is_full:
        await message.reply_text(get_message("queued", lang))

    start = time.monotonic()
    status = "ok"
    video_info: VideoInfo | None = None
    sent_file_size: int | None = None
    file_path: str | None = None
    slideshow: SlideshowResult | None = None
    try:
        async with queue.acquire():
            metadata = await extract_metadata(url)
            video_info = metadata.info

            # Validate format compatibility before downloading
            if metadata.duration and metadata.duration > settings.max_duration:
                status = "too_long"
                await message.reply_text(get_message("error_too_long", lang))
                return
            if (
                metadata.file_size
                and metadata.file_size > settings.max_file_size * 1024 * 1024
            ):
                status = "too_large"
                await message.reply_text(get_message("error_too_large", lang))
                return

            if output_format == OutputFormat.IMAGES and not metadata.is_slideshow:
                status = "not_slideshow"
                await message.reply_text(get_message("error_not_slideshow", lang))
                return

            if output_format == OutputFormat.AUDIO:
                # Audio extraction from any content type
                status_msg = await message.reply_text(
                    get_message("downloading_audio", lang)
                )
                await context.bot.send_chat_action(
                    chat_id=message.chat_id, action=ChatAction.UPLOAD_VOICE
                )
                audio_result = await download_audio(url, settings.download_dir)
                file_path = audio_result.audio_path
                sent_file_size = os.path.getsize(file_path)

                await status_msg.edit_text(get_message("sending_audio", lang))
                await context.bot.send_chat_action(
                    chat_id=message.chat_id, action=ChatAction.UPLOAD_VOICE
                )
                with open(audio_result.audio_path, "rb") as audio_file:
                    await message.reply_audio(
                        audio=audio_file,
                        title=audio_result.title,
                        reply_to_message_id=reply_to,
                    )
                await status_msg.delete()

            elif metadata.is_slideshow:
                if output_format == OutputFormat.IMAGES:
                    # Images only, no audio
                    status_msg = await message.reply_text(
                        get_message("downloading_photos", lang)
                    )
                    await context.bot.send_chat_action(
                        chat_id=message.chat_id, action=ChatAction.UPLOAD_PHOTO
                    )
                    slideshow = await download_slideshow(
                        url, settings.download_dir, include_audio=False
                    )
                    await status_msg.edit_text(get_message("sending_photos", lang))
                    await context.bot.send_chat_action(
                        chat_id=message.chat_id, action=ChatAction.UPLOAD_PHOTO
                    )
                    # Send only images (no audio)
                    for batch_start in range(0, len(slideshow.image_paths), 10):
                        batch = slideshow.image_paths[batch_start : batch_start + 10]
                        handles = [open(p, "rb") for p in batch]  # noqa: SIM115
                        media = [InputMediaPhoto(media=h) for h in handles]
                        try:
                            await message.reply_media_group(
                                media=media,
                                reply_to_message_id=reply_to,
                            )
                        finally:
                            for h in handles:
                                h.close()
                    await status_msg.delete()
                else:
                    # DEFAULT: images + audio
                    status_msg = await message.reply_text(
                        get_message("downloading_photos", lang)
                    )
                    await context.bot.send_chat_action(
                        chat_id=message.chat_id, action=ChatAction.UPLOAD_PHOTO
                    )
                    slideshow = await download_slideshow(url, settings.download_dir)
                    await status_msg.edit_text(get_message("sending_photos", lang))
                    await context.bot.send_chat_action(
                        chat_id=message.chat_id, action=ChatAction.UPLOAD_PHOTO
                    )
                    await _send_slideshow(message, slideshow, reply_to=reply_to)
                    await status_msg.delete()
            else:
                # DEFAULT + video
                status_msg = await message.reply_text(
                    get_message("downloading", lang)
                )
                await context.bot.send_chat_action(
                    chat_id=message.chat_id, action=ChatAction.UPLOAD_VIDEO
                )

                file_path = await download_video(url, settings.download_dir)

                actual_size = os.path.getsize(file_path)
                if actual_size > settings.max_file_size * 1024 * 1024:
                    status = "too_large"
                    await status_msg.edit_text(get_message("error_too_large", lang))
                    return
                sent_file_size = actual_size

                await status_msg.edit_text(get_message("sending", lang))
                await context.bot.send_chat_action(
                    chat_id=message.chat_id, action=ChatAction.UPLOAD_VIDEO
                )
                with open(file_path, "rb") as video_file:
                    await message.reply_video(
                        video=video_file,
                        supports_streaming=True,
                        reply_to_message_id=reply_to,
                    )
                await status_msg.delete()

    except VideoDownloadError as e:
        status = e.error_type.value
        msg_key = _ERROR_TYPE_TO_MESSAGE_KEY.get(e.error_type, "error_download")
        await message.reply_text(get_message(msg_key, lang))
    except Exception:
        status = "unknown_error"
        log.exception("request.unhandled_error")
        await message.reply_text(get_message("error_unknown", lang))
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        if slideshow:
            _cleanup_slideshow(slideshow)
        user = message.from_user
        analytics.record(
            DownloadEvent(
                user_id=user.id if user else 0,
                chat_type="private" if message.chat.type == "private" else "group",
                platform=platform.value,
                url=url,
                output_format=output_format.value,
                status=status,
                video_id=video_info.video_id if video_info else None,
                duration_ms=int((time.monotonic() - start) * 1000),
                file_size_bytes=sent_file_size,
            ),
            video_info,
        )
```

Note the variable rename in the destructure: `url, platform = result` (was `url, _platform = result`).

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest tests/ -v`
Expected: all PASS — both the new capture tests and the existing routing matrix.

- [ ] **Step 5: Lint, type-check, commit**

Run: `uv run ruff check . && uv run mypy`

```bash
git add src/bot/handlers/common.py tests/unit/test_analytics_capture.py tests/unit/test_handler_routing.py
git commit -m "feat: record analytics event on every process_request exit path"
```

---

### Task 5: Capture point in `handle_inline_query()`

**Files:**
- Modify: `src/bot/handlers/inline.py`
- Test: append to `tests/unit/test_analytics_capture.py`

**Interfaces:**
- Consumes: same as Task 4.
- Produces: one event per inline download attempt, `chat_type="inline"`, `output_format="default"` always (inline has no format keywords). The inline slideshow rejection records `status="not_slideshow"`; the missing-file_id fallback records `status="download_error"`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_analytics_capture.py`:

```python
@pytest.mark.asyncio
async def test_inline_error_records_event():
    from bot.handlers.inline import handle_inline_query

    ctx = _make_context()
    ctx.bot_data["user_store"] = MagicMock()
    ctx.bot_data["user_store"].is_allowed.return_value = True

    update = MagicMock()
    query = update.inline_query
    query.from_user.id = 42
    query.from_user.language_code = "en"
    query.query = VIDEO_URL
    query.answer = AsyncMock()

    with (
        patch("bot.handlers.inline.extract_url", return_value=(VIDEO_URL, Platform.TIKTOK)),
        patch(
            "bot.handlers.inline.extract_metadata",
            side_effect=VideoDownloadError(ErrorType.PRIVATE),
        ),
    ):
        await handle_inline_query(update, ctx)

    event, _ = _recorded_event(ctx)
    assert event.status == "private"
    assert event.chat_type == "inline"
    assert event.output_format == "default"
    assert event.user_id == 42
```

Run: `uv run pytest tests/unit/test_analytics_capture.py -v -k inline`
Expected: FAIL — `record` never called

- [ ] **Step 2: Implement**

In `src/bot/handlers/inline.py`, add imports:

```python
from bot.models.video_info import VideoInfo
from bot.services.analytics import Analytics, DownloadEvent
```

Inside `handle_inline_query`, after `url, _platform = result` → rename to `url, platform = result`, and fetch `analytics: Analytics = context.bot_data["analytics"]` next to the `queue` lookup.

Add outcome state right after the queue lookup:

```python
    status = "ok"
    video_info: VideoInfo | None = None
    sent_file_size: int | None = None
```

Set state in each branch (existing logic untouched otherwise):

- after `metadata = await extract_metadata(url)`: `video_info = metadata.info`
- slideshow rejection: `status = "not_slideshow"` before the answer/return
- duration rejection: `status = "too_long"`
- pre-download size rejection: `status = "too_large"`
- post-download size rejection: `status = "too_large"`, and on the success path `sent_file_size = actual_size`
- missing `file_id` fallback: `status = "download_error"`
- `except VideoDownloadError as e:` → `status = e.error_type.value`
- `except Exception:` → `status = "unknown_error"`

In the existing `finally` block, record before the contextvars unbind (reusing the duration it already computes):

```python
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        duration_ms = int((time.monotonic() - start_time) * 1000)
        analytics.record(
            DownloadEvent(
                user_id=user.id,
                chat_type="inline",
                platform=platform.value,
                url=url,
                output_format="default",
                status=status,
                video_id=video_info.video_id if video_info else None,
                duration_ms=duration_ms,
                file_size_bytes=sent_file_size,
            ),
            video_info,
        )
        log.info("request.completed", total_duration_ms=duration_ms)
        structlog.contextvars.unbind_contextvars(
            "request_id", "user_id", "chat_type", "language"
        )
```

Careful: the `finally` belongs to the `try` that wraps the queue/download section — the early returns before it (whitelist, no-URL help) correctly record nothing.

- [ ] **Step 3: Run the full suite**

Run: `uv run pytest tests/ -v`
Expected: all PASS

- [ ] **Step 4: Lint, type-check, commit**

Run: `uv run ruff check . && uv run mypy`

```bash
git add src/bot/handlers/inline.py tests/unit/test_analytics_capture.py
git commit -m "feat: record analytics events for inline mode"
```

---

### Task 6: Wire Analytics in `__main__`, compose `db` network, docs

**Files:**
- Modify: `src/bot/__main__.py`
- Modify: `docker-compose.yml`
- Modify: `README.md` (config table), `CLAUDE.md` (Recent Changes + structure)

**Interfaces:**
- Consumes: `Analytics`, `Settings.analytics_dsn` (Task 3).
- Produces: `context.bot_data["analytics"]` present in production (Tasks 4–5 rely on it); schema ensured via PTB `post_init`; pool closed via `post_shutdown`.

- [ ] **Step 1: Wire in `src/bot/__main__.py`**

Add import:

```python
from bot.services.analytics import Analytics
```

In `main()`, before the `Application.builder()` call:

```python
    analytics = Analytics(
        settings.analytics_dsn.get_secret_value() if settings.analytics_dsn else None
    )

    async def _post_init(app_: object) -> None:
        await analytics.ensure_schema()

    async def _post_shutdown(app_: object) -> None:
        await analytics.close()
```

Extend the builder chain and bot_data:

```python
    app = (
        Application.builder()
        .token(settings.bot_token.get_secret_value())
        .concurrent_updates(True)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )
```

```python
    app.bot_data["analytics"] = analytics
```

Also add `analytics_enabled=analytics.enabled` to the existing `log.info("bot.starting", ...)` call.

- [ ] **Step 2: Verify import and suite**

Run: `uv run python -c "import bot.__main__"` (from repo root; if `bot` isn't importable this way, use `cd src && uv run python -c "import bot.__main__"`)
Expected: no output, exit 0

Run: `uv run pytest tests/ -v && uv run ruff check . && uv run mypy`
Expected: all clean

- [ ] **Step 3: Compose — join the external `db` network**

`docker-compose.yml` — add `networks` to the `bot` service and a top-level `networks` block. Listing `default` explicitly is required: naming any network on the service drops the implicit default, and the bot needs outbound internet.

```yaml
services:
  bot:
    build: .
    restart: unless-stopped
    env_file: .env
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    mem_limit: 768m
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import os,time,sys; sys.exit(0 if time.time()-os.path.getmtime('/app/src/data/heartbeat')<90 else 1)\""]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 40s
    volumes:
      - downloads:/tmp/tg-bot-downloads
      - botdata:/app/src/data
    networks:
      - default
      - db
volumes:
  downloads:
  botdata:
networks:
  db:
    external: true
```

Local check (the `db` network won't exist locally — validate syntax only):
Run: `docker compose config --quiet`
Expected: exit 0 (warning about the external network is acceptable)

- [ ] **Step 4: Docs**

- `README.md`: add `ANALYTICS_DSN` to the configuration section — "optional; Postgres DSN for usage analytics (e.g. `postgresql://user:pass@host:5432/dbname`); unset = analytics disabled."
- `CLAUDE.md`: add `analytics.py` and `models/video_info.py` to the project-structure tree; add a Recent Changes line: `003-analytics-data-layer: download events + video metadata into shared Postgres (asyncpg, fire-and-forget)`.

- [ ] **Step 5: Commit**

```bash
git add src/bot/__main__.py docker-compose.yml README.md CLAUDE.md
git commit -m "feat: wire analytics into app lifecycle and join db network"
```

---

### Task 7: Provision Postgres + deploy + live verification

Operational task — no TDD cycle. Touches the **postgres repo** (`~/petprojects/postgres`, local-only git) and the server. The public bot repo must never contain the generated password.

**Files:**
- Modify: `~/petprojects/postgres/initdb/01-apps.sh`
- Modify: `~/petprojects/postgres/docker-compose.yml` (environment block)
- Server: `/home/abilay/postgres/.env`, `/home/abilay/tiktok-tg-bot/.env`

- [ ] **Step 1: Update the postgres repo (local)**

Append to the heredoc in `~/petprojects/postgres/initdb/01-apps.sh`:

```bash
  CREATE USER tiktokbot WITH PASSWORD '${TIKTOKBOT_DB_PASSWORD}';
  CREATE DATABASE tiktokbot OWNER tiktokbot;
```

Add to the `environment:` block of `~/petprojects/postgres/docker-compose.yml`:

```yaml
      TIKTOKBOT_DB_PASSWORD: ${TIKTOKBOT_DB_PASSWORD}
```

Commit in that repo:

```bash
cd ~/petprojects/postgres
git add initdb/01-apps.sh docker-compose.yml
git commit -m "feat: provision tiktokbot database for bot analytics"
```

- [ ] **Step 2: Create the DB/user on the live server**

initdb scripts only run on a fresh volume, so create manually (same procedure as the kurakkorpe migration). Generate a password locally (`openssl rand -hex 24`), then:

```bash
ssh hetzner-deploy
# 1) append to /home/abilay/postgres/.env:
#    TIKTOKBOT_DB_PASSWORD=<generated>
# 2) create user + database (password inline — runs on the server only):
docker exec -i postgres psql -U postgres <<'SQL'
CREATE USER tiktokbot WITH PASSWORD '<generated>';
CREATE DATABASE tiktokbot OWNER tiktokbot;
SQL
```

Sync the repo changes to the server dir (rsync per house pattern, or copy the two edited files). Do NOT `docker compose up -d` on the postgres stack now — the env var only matters for future fresh-volume rebuilds, and recreating the container briefly drops miniflux/linkding/kurak-korpe. It gets picked up on the next natural restart.

- [ ] **Step 3: Configure and deploy the bot**

```bash
# on the server: append to /home/abilay/tiktok-tg-bot/.env
ANALYTICS_DSN=postgresql://tiktokbot:<generated>@postgres:5432/tiktokbot
```

Push and deploy (bot deploys via git pull — commit must be on `origin/master` first):

```bash
cd ~/petprojects/tiktok-tg-bot
git push origin master
cd ~/petprojects && make deploy-bot
```

Note: `docker compose up -d --build` (inside deploy-bot) is required — a plain `restart` does not reload `.env`.

- [ ] **Step 4: Live verification**

1. Startup: `ssh hetzner-deploy "cd ~/tiktok-tg-bot && docker compose logs --tail 50 bot"` — expect `analytics.schema_ready` and no `analytics.schema_failed`.
2. Send through Telegram: one TikTok video link, one `audio <link>`, one YouTube Short, one Instagram Reel, one dead/private link.
3. Check rows:

```bash
ssh hetzner-deploy "docker exec postgres psql -U tiktokbot -d tiktokbot -c \
  'SELECT status, platform, output_format, count(*) FROM download_events GROUP BY 1,2,3;'"
ssh hetzner-deploy "docker exec postgres psql -U tiktokbot -d tiktokbot -c \
  'SELECT platform, video_id, author_handle, hashtags FROM videos;'"
```

Expected: one event per sent link with correct status/platform/format; `videos` rows populated with hashtags/authors for the successful ones.

4. Update the vault note (`~/vault/petprojects/tiktok-tg-bot.md`) — **only when the owner says to log it**, per vault rules.

---

## Self-Review Notes

- Spec coverage: schema §1 → Task 3 DDL; VideoInfo capture §2 → Tasks 1–2; write path §3 → Task 3; capture points §4 → Tasks 4–5; config & infra §5 → Tasks 3 (dsn), 6 (compose), 7 (postgres repo, server); testing §6 → Tasks 1–5 + live verification in Task 7. Non-goals untouched.
- `status` vocabulary is identical across spec, Task 4, and Task 5: `ok`, `too_long`, `too_large`, `not_slideshow`, `ErrorType.value` set, `unknown_error`.
- Type consistency: `DownloadEvent` field names in Tasks 4/5 match the Task 3 dataclass; `VideoInfo.from_info_dict(info, url)` signature consistent in Tasks 1/2.
