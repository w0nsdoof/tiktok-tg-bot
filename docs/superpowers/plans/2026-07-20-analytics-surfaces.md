# Analytics Surfaces Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface the analytics captured by sub-project A: a provisioned Grafana dashboard reading the `tiktokbot` Postgres DB, plus `/stats` and `/top` bot commands.

**Architecture:** A read-only `StatsService` in the bot shares the existing `Analytics` asyncpg pool (write path untouched). Grafana connects through a new SELECT-only role `tiktokbot_ro` via a provisioned postgres datasource (uid `tiktokbot`) and one provisioned dashboard JSON. Three repos are touched: `tiktok-tg-bot` (code), `monitoring` (Grafana config), `postgres` (initdb parity only, no deploy).

**Tech Stack:** Python 3.12, python-telegram-bot 21.x, asyncpg (already a dependency), plain SQL, Grafana provisioning (YAML + dashboard JSON).

**Spec:** `docs/superpowers/specs/2026-07-20-analytics-surfaces-design.md`

## Global Constraints

- No new Python dependencies. Plain SQL strings, no ORM, no migration framework.
- Every user-facing string exists in **both** `en` and `ru` in `src/bot/locales/messages.py`. Replies are plain text — this bot never uses `parse_mode`.
- `/stats` and `/top` are **private chat + whitelist only** (same filter pattern as `/help`).
- Fixed names (exact): role `tiktokbot_ro`, env var `TIKTOKBOT_RO_PASSWORD`, datasource uid `tiktokbot`, dashboard uid `tiktok-bot`.
- Read queries use a 5-second timeout (`timeout=5` on `conn.fetch`). Handlers never raise — any query failure logs a warning and replies with a localized "unavailable" message.
- Secrets never enter git. The RO password lives only in server-side `/home/abilay/monitoring/.env` and in Postgres itself.
- Grafana provisioning gotcha (vault `~/vault/petprojects/monitoring.md`): env interpolation only for non-numeric secrets; numeric settings stay YAML literals.
- Deploys only via `make -C ~/petprojects <target>`. **Never run `deploy-postgres`** — the postgres-repo change is committed but its rollout is owner-timed (recreates the shared DB container).
- Bot repo commands (from repo root `~/petprojects/tiktok-tg-bot`): targeted test `cd src && uv run pytest ../tests/unit/<file>.py -v`; full suite `cd src && uv run pytest`; lint `cd src && uv run ruff check .` (line length 100).
- Commit after every task. Bot commits stay local until Task 7 (`git push` is the deploy gate — `make deploy-bot` pulls from GitHub).
- Server access: `ssh hetzner-deploy` (non-root `abilay`, has docker). Data volume is tiny (capture started 2026-07-20) — sparse dashboards/stats are expected, not a bug.

---

### Task 1: `Analytics.get_pool()` accessor

**Files:**
- Modify: `src/bot/services/analytics.py` (class `Analytics`, after the `enabled` property)
- Test: `tests/unit/test_analytics.py`

**Interfaces:**
- Consumes: existing `Analytics._get_pool()` / `Analytics.enabled`.
- Produces: `async def get_pool(self) -> Any` — returns the shared asyncpg pool, or `None` when disabled. Task 2's `StatsService` calls this.

- [ ] **Step 1: Write the failing tests** — append to `tests/unit/test_analytics.py`:

```python
class TestGetPool:
    @pytest.mark.asyncio
    async def test_disabled_returns_none(self):
        assert await Analytics(None).get_pool() is None

    @pytest.mark.asyncio
    async def test_enabled_returns_shared_pool(self):
        analytics = Analytics("postgresql://ignored")
        pool = _FakePool(AsyncMock())
        analytics._pool = pool
        assert await analytics.get_pool() is pool
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd src && uv run pytest ../tests/unit/test_analytics.py -v -k TestGetPool`
Expected: FAIL — `AttributeError: 'Analytics' object has no attribute 'get_pool'`

- [ ] **Step 3: Implement** — add to `Analytics` right after the `enabled` property:

```python
    async def get_pool(self) -> Any:
        """Shared pool for read-side services (StatsService). None when disabled."""
        if not self.enabled:
            return None
        return await self._get_pool()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd src && uv run pytest ../tests/unit/test_analytics.py -v`
Expected: all PASS (new + pre-existing)

- [ ] **Step 5: Commit**

```bash
git add src/bot/services/analytics.py tests/unit/test_analytics.py
git commit -m "feat: expose Analytics pool for read-side services"
```

---

### Task 2: `StatsService` — user and global stats

**Files:**
- Create: `src/bot/services/stats.py`
- Test: `tests/unit/test_stats_service.py`

**Interfaces:**
- Consumes: `Analytics.get_pool()` (Task 1), `Analytics.enabled`.
- Produces (used by Tasks 3, 5, 6):
  - `@dataclass UserStats(requests: int, downloads: int, first_use: datetime | None, platforms: list[tuple[str, int]], creators: list[tuple[str, int]], hashtags: list[tuple[str, int]])`
  - `@dataclass GlobalStats(users: int, requests: int, downloads: int, top_users: list[tuple[int, int]], platforms: list[tuple[str, int]], creators: list[tuple[str, int]], hashtags: list[tuple[str, int]])`
  - `class StatsService: __init__(analytics: Analytics)`, `enabled: bool` property, `async user_stats(user_id: int) -> UserStats`, `async global_stats() -> GlobalStats`, and the private `async _fetch(query, *args)` helper Task 3 reuses.

- [ ] **Step 1: Write the failing tests** — create `tests/unit/test_stats_service.py`:

```python
"""Tests for the read-side StatsService (fake pool, no Postgres)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

from bot.services.analytics import Analytics
from bot.services.stats import GlobalStats, StatsService, UserStats


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd src && uv run pytest ../tests/unit/test_stats_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.services.stats'`

- [ ] **Step 3: Implement** — create `src/bot/services/stats.py`:

```python
"""Read-side analytics queries for /stats and /top. Shares the Analytics pool."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import structlog

from bot.services.analytics import Analytics

log = structlog.get_logger()

_QUERY_TIMEOUT = 5  # seconds

_USER_SUMMARY = """
SELECT count(*) AS requests,
       count(*) FILTER (WHERE status = 'ok') AS downloads,
       min(ts) AS first_use
FROM download_events
WHERE user_id = $1
"""

_USER_PLATFORMS = """
SELECT platform, count(*) AS n
FROM download_events
WHERE user_id = $1 AND status = 'ok'
GROUP BY platform
ORDER BY n DESC
LIMIT 3
"""

_USER_CREATORS = """
SELECT coalesce(v.author_handle, v.author_name, 'unknown') AS name, count(*) AS n
FROM download_events e
JOIN videos v ON v.platform = e.platform AND v.video_id = e.video_id
WHERE e.user_id = $1 AND e.status = 'ok'
GROUP BY 1
ORDER BY n DESC
LIMIT 5
"""

_USER_HASHTAGS = """
SELECT tag AS name, count(*) AS n
FROM download_events e
JOIN videos v ON v.platform = e.platform AND v.video_id = e.video_id
CROSS JOIN LATERAL unnest(v.hashtags) AS tag
WHERE e.user_id = $1 AND e.status = 'ok'
GROUP BY tag
ORDER BY n DESC
LIMIT 5
"""

_GLOBAL_SUMMARY = """
SELECT count(DISTINCT user_id) AS users,
       count(*) AS requests,
       count(*) FILTER (WHERE status = 'ok') AS downloads
FROM download_events
"""

_GLOBAL_TOP_USERS = """
SELECT user_id, count(*) FILTER (WHERE status = 'ok') AS n
FROM download_events
GROUP BY user_id
ORDER BY n DESC
LIMIT 5
"""

_GLOBAL_PLATFORMS = """
SELECT platform, count(*) AS n
FROM download_events
WHERE status = 'ok'
GROUP BY platform
ORDER BY n DESC
LIMIT 3
"""

_GLOBAL_CREATORS = """
SELECT coalesce(v.author_handle, v.author_name, 'unknown') AS name, count(*) AS n
FROM download_events e
JOIN videos v ON v.platform = e.platform AND v.video_id = e.video_id
WHERE e.status = 'ok'
GROUP BY 1
ORDER BY n DESC
LIMIT 5
"""

_GLOBAL_HASHTAGS = """
SELECT tag AS name, count(*) AS n
FROM download_events e
JOIN videos v ON v.platform = e.platform AND v.video_id = e.video_id
CROSS JOIN LATERAL unnest(v.hashtags) AS tag
WHERE e.status = 'ok'
GROUP BY tag
ORDER BY n DESC
LIMIT 5
"""


@dataclass
class UserStats:
    requests: int
    downloads: int
    first_use: datetime | None
    platforms: list[tuple[str, int]]
    creators: list[tuple[str, int]]
    hashtags: list[tuple[str, int]]


@dataclass
class GlobalStats:
    users: int
    requests: int
    downloads: int
    top_users: list[tuple[int, int]]
    platforms: list[tuple[str, int]]
    creators: list[tuple[str, int]]
    hashtags: list[tuple[str, int]]


class StatsService:
    """Read-only queries over the analytics tables. Never writes."""

    def __init__(self, analytics: Analytics) -> None:
        self._analytics = analytics

    @property
    def enabled(self) -> bool:
        return self._analytics.enabled

    async def _fetch(self, query: str, *args: Any) -> list[Any]:
        pool = await self._analytics.get_pool()
        async with pool.acquire() as conn:
            return await conn.fetch(query, *args, timeout=_QUERY_TIMEOUT)

    async def user_stats(self, user_id: int) -> UserStats:
        summary = (await self._fetch(_USER_SUMMARY, user_id))[0]
        platforms = await self._fetch(_USER_PLATFORMS, user_id)
        creators = await self._fetch(_USER_CREATORS, user_id)
        hashtags = await self._fetch(_USER_HASHTAGS, user_id)
        return UserStats(
            requests=summary["requests"],
            downloads=summary["downloads"],
            first_use=summary["first_use"],
            platforms=[(r["platform"], r["n"]) for r in platforms],
            creators=[(r["name"], r["n"]) for r in creators],
            hashtags=[(r["name"], r["n"]) for r in hashtags],
        )

    async def global_stats(self) -> GlobalStats:
        summary = (await self._fetch(_GLOBAL_SUMMARY))[0]
        top_users = await self._fetch(_GLOBAL_TOP_USERS)
        platforms = await self._fetch(_GLOBAL_PLATFORMS)
        creators = await self._fetch(_GLOBAL_CREATORS)
        hashtags = await self._fetch(_GLOBAL_HASHTAGS)
        return GlobalStats(
            users=summary["users"],
            requests=summary["requests"],
            downloads=summary["downloads"],
            top_users=[(r["user_id"], r["n"]) for r in top_users],
            platforms=[(r["platform"], r["n"]) for r in platforms],
            creators=[(r["name"], r["n"]) for r in creators],
            hashtags=[(r["name"], r["n"]) for r in hashtags],
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd src && uv run pytest ../tests/unit/test_stats_service.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/bot/services/stats.py tests/unit/test_stats_service.py
git commit -m "feat: StatsService with per-user and global analytics reads"
```

---

### Task 3: `StatsService` — tops (tags, creators, videos-for-tag)

**Files:**
- Modify: `src/bot/services/stats.py`
- Test: `tests/unit/test_stats_service.py`

**Interfaces:**
- Consumes: `StatsService._fetch` (Task 2).
- Produces (used by Task 6):
  - `@dataclass TagVideo(title: str | None, creator: str, like_count: int | None, url: str)`
  - `async top_tags(limit: int) -> list[tuple[str, int]]`
  - `async top_creators(limit: int) -> list[tuple[str, int]]`
  - `async top_videos_for_tag(tag: str, limit: int) -> list[TagVideo]` (expects an already-lowercased tag without `#` — A stores hashtags lowercased)

- [ ] **Step 1: Write the failing tests** — append to `tests/unit/test_stats_service.py` (add `TagVideo` to the existing `bot.services.stats` import):

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd src && uv run pytest ../tests/unit/test_stats_service.py -v -k TestTops`
Expected: FAIL — `ImportError: cannot import name 'TagVideo'`

- [ ] **Step 3: Implement** — add to `src/bot/services/stats.py` (queries next to the others, dataclass next to the others, methods on `StatsService`):

```python
_TOP_TAGS = """
SELECT tag AS name, count(*) AS n
FROM download_events e
JOIN videos v ON v.platform = e.platform AND v.video_id = e.video_id
CROSS JOIN LATERAL unnest(v.hashtags) AS tag
WHERE e.status = 'ok'
GROUP BY tag
ORDER BY n DESC
LIMIT $1
"""

_TOP_CREATORS = """
SELECT coalesce(v.author_handle, v.author_name, 'unknown') AS name, count(*) AS n
FROM download_events e
JOIN videos v ON v.platform = e.platform AND v.video_id = e.video_id
WHERE e.status = 'ok'
GROUP BY 1
ORDER BY n DESC
LIMIT $1
"""

_TAG_VIDEOS = """
SELECT v.title,
       coalesce(v.author_handle, v.author_name, 'unknown') AS creator,
       v.like_count,
       v.url
FROM videos v
WHERE $1 = ANY(v.hashtags)
ORDER BY v.like_count DESC NULLS LAST
LIMIT $2
"""


@dataclass
class TagVideo:
    title: str | None
    creator: str
    like_count: int | None
    url: str
```

```python
    async def top_tags(self, limit: int) -> list[tuple[str, int]]:
        rows = await self._fetch(_TOP_TAGS, limit)
        return [(r["name"], r["n"]) for r in rows]

    async def top_creators(self, limit: int) -> list[tuple[str, int]]:
        rows = await self._fetch(_TOP_CREATORS, limit)
        return [(r["name"], r["n"]) for r in rows]

    async def top_videos_for_tag(self, tag: str, limit: int) -> list[TagVideo]:
        rows = await self._fetch(_TAG_VIDEOS, tag, limit)
        return [
            TagVideo(
                title=r["title"],
                creator=r["creator"],
                like_count=r["like_count"],
                url=r["url"],
            )
            for r in rows
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd src && uv run pytest ../tests/unit/test_stats_service.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/bot/services/stats.py tests/unit/test_stats_service.py
git commit -m "feat: StatsService top tags, creators, and videos-for-tag"
```

---

### Task 4: Locale strings for /stats and /top + /help mention

**Files:**
- Modify: `src/bot/locales/messages.py` (both `en` and `ru` dicts, and the two existing `help` entries)
- Test: `tests/unit/test_stats_messages.py` (create)

**Interfaces:**
- Consumes: existing `get_message(key, lang, **kwargs)`.
- Produces message keys used by Tasks 5–6 (exact placeholder names matter): `stats_unavailable`, `stats_empty`, `stats_personal` (`requests, downloads, since, platforms, creators, hashtags`), `stats_global` (`users, requests, downloads, top_users, platforms, creators, hashtags`), `top_usage`, `top_tags_title` (`items`), `top_creators_title` (`items`), `top_videos_title` (`tag, items`), `top_empty`.

- [ ] **Step 1: Write the failing test** — create `tests/unit/test_stats_messages.py`:

```python
"""Locale coverage for /stats and /top strings."""

import pytest

from bot.locales.messages import MESSAGES, get_message

STATS_KEYS = [
    "stats_unavailable",
    "stats_empty",
    "stats_personal",
    "stats_global",
    "top_usage",
    "top_tags_title",
    "top_creators_title",
    "top_videos_title",
    "top_empty",
]


@pytest.mark.parametrize("key", STATS_KEYS)
def test_key_exists_in_both_languages(key):
    assert key in MESSAGES["en"]
    assert key in MESSAGES["ru"]


def test_personal_template_formats():
    text = get_message(
        "stats_personal",
        "en",
        requests=10,
        downloads=8,
        since="2026-07-20",
        platforms="1. tiktok — 6",
        creators="1. @cat — 3",
        hashtags="1. #fyp — 4",
    )
    assert "10" in text and "@cat" in text


def test_help_mentions_new_commands():
    for lang in ("en", "ru"):
        assert "/stats" in MESSAGES[lang]["help"]
        assert "/top" in MESSAGES[lang]["help"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src && uv run pytest ../tests/unit/test_stats_messages.py -v`
Expected: FAIL — missing keys

- [ ] **Step 3: Implement** — add to the `en` dict in `src/bot/locales/messages.py`:

```python
        "stats_unavailable": "Stats are unavailable right now. Please try again later.",
        "stats_empty": "No downloads recorded yet — send me a link first!",
        "stats_personal": (
            "📊 Your stats\n"
            "Requests: {requests}\n"
            "Successful downloads: {downloads}\n"
            "First use: {since}\n\n"
            "Top platforms:\n{platforms}\n\n"
            "Top creators:\n{creators}\n\n"
            "Top hashtags:\n{hashtags}"
        ),
        "stats_global": (
            "📊 Global stats\n"
            "Users: {users}\n"
            "Requests: {requests}\n"
            "Successful downloads: {downloads}\n\n"
            "Top users:\n{top_users}\n\n"
            "Top platforms:\n{platforms}\n\n"
            "Top creators:\n{creators}\n\n"
            "Top hashtags:\n{hashtags}"
        ),
        "top_usage": (
            "Usage:\n"
            "/top tags — top hashtags\n"
            "/top creators — top creators\n"
            "/top #hashtag — top videos for a hashtag"
        ),
        "top_tags_title": "🏷 Top hashtags:\n{items}",
        "top_creators_title": "👤 Top creators:\n{items}",
        "top_videos_title": "🔥 Top videos for #{tag}:\n{items}",
        "top_empty": "No data yet.",
```

and to the `ru` dict:

```python
        "stats_unavailable": "Статистика сейчас недоступна. Попробуйте позже.",
        "stats_empty": "Пока нет загрузок — сначала отправьте мне ссылку!",
        "stats_personal": (
            "📊 Ваша статистика\n"
            "Запросов: {requests}\n"
            "Успешных загрузок: {downloads}\n"
            "Первое использование: {since}\n\n"
            "Топ платформ:\n{platforms}\n\n"
            "Топ авторов:\n{creators}\n\n"
            "Топ хэштегов:\n{hashtags}"
        ),
        "stats_global": (
            "📊 Общая статистика\n"
            "Пользователей: {users}\n"
            "Запросов: {requests}\n"
            "Успешных загрузок: {downloads}\n\n"
            "Топ пользователей:\n{top_users}\n\n"
            "Топ платформ:\n{platforms}\n\n"
            "Топ авторов:\n{creators}\n\n"
            "Топ хэштегов:\n{hashtags}"
        ),
        "top_usage": (
            "Использование:\n"
            "/top tags — топ хэштегов\n"
            "/top creators — топ авторов\n"
            "/top #хэштег — топ видео по хэштегу"
        ),
        "top_tags_title": "🏷 Топ хэштегов:\n{items}",
        "top_creators_title": "👤 Топ авторов:\n{items}",
        "top_videos_title": "🔥 Топ видео по #{tag}:\n{items}",
        "top_empty": "Пока нет данных.",
```

Extend the existing `help` strings — append to the `en` `help` value:

```python
            "\n\n/stats — your download stats\n"
            "/top tags | creators | #hashtag — leaderboards"
```

and to the `ru` `help` value:

```python
            "\n\n/stats — ваша статистика загрузок\n"
            "/top tags | creators | #хэштег — рейтинги"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd src && uv run pytest ../tests/unit/test_stats_messages.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/bot/locales/messages.py tests/unit/test_stats_messages.py
git commit -m "feat: EN/RU locale strings for /stats and /top"
```

---

### Task 5: `/stats` handler + registration

**Files:**
- Create: `src/bot/handlers/stats.py`
- Modify: `src/bot/__main__.py`
- Test: `tests/unit/test_stats_handlers.py` (create)

**Interfaces:**
- Consumes: `StatsService.user_stats/global_stats` + dataclasses (Task 2), locale keys (Task 4), `UserStore.is_admin`, `context.bot_data["stats"]` and `["user_store"]`.
- Produces: `async handle_stats(update, context)`, module-level helper `_ranked(items) -> str` (Task 6 reuses both file and helper); `bot_data["stats"]` wired in `__main__.py`.

- [ ] **Step 1: Write the failing tests** — create `tests/unit/test_stats_handlers.py`:

```python
"""Tests for /stats and /top handlers (mocked service, no Postgres)."""

from unittest.mock import AsyncMock, MagicMock

from bot.handlers.stats import handle_stats
from bot.services.stats import GlobalStats, UserStats

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd src && uv run pytest ../tests/unit/test_stats_handlers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.handlers.stats'`

- [ ] **Step 3: Implement** — create `src/bot/handlers/stats.py`:

```python
"""/stats and /top command handlers (read-side analytics)."""

import structlog
from telegram import Update
from telegram.ext import ContextTypes

from bot.locales.messages import get_message
from bot.services.stats import StatsService

log = structlog.get_logger()


def _ranked(items: list) -> str:
    if not items:
        return "—"
    return "\n".join(f"{i}. {name} — {n}" for i, (name, n) in enumerate(items, 1))


async def handle_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_user:
        return
    user = update.effective_user
    lang = user.language_code
    stats: StatsService = context.bot_data["stats"]
    if not stats.enabled:
        await update.effective_message.reply_text(get_message("stats_unavailable", lang))
        return
    user_store = context.bot_data["user_store"]
    want_global = bool(context.args) and context.args[0].lower() == "all"
    try:
        if want_global and user_store.is_admin(user.id):
            g = await stats.global_stats()
            text = get_message(
                "stats_global",
                lang,
                users=g.users,
                requests=g.requests,
                downloads=g.downloads,
                top_users=_ranked(g.top_users),
                platforms=_ranked(g.platforms),
                creators=_ranked(g.creators),
                hashtags=_ranked(g.hashtags),
            )
        else:
            s = await stats.user_stats(user.id)
            if s.requests == 0:
                await update.effective_message.reply_text(get_message("stats_empty", lang))
                return
            text = get_message(
                "stats_personal",
                lang,
                requests=s.requests,
                downloads=s.downloads,
                since=s.first_use.date().isoformat() if s.first_use else "—",
                platforms=_ranked(s.platforms),
                creators=_ranked(s.creators),
                hashtags=_ranked(s.hashtags),
            )
    except Exception:
        log.warning("stats.query_failed", exc_info=True)
        await update.effective_message.reply_text(get_message("stats_unavailable", lang))
        return
    await update.effective_message.reply_text(text)
```

Wire into `src/bot/__main__.py`:
- Add imports: `from bot.handlers.stats import handle_stats` and `from bot.services.stats import StatsService`.
- After `app.bot_data["analytics"] = analytics` add: `app.bot_data["stats"] = StatsService(analytics)`.
- With the other private-chat handlers add:

```python
    app.add_handler(CommandHandler("stats", handle_stats, filters=private & whitelist))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd src && uv run pytest ../tests/unit/test_stats_handlers.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/bot/handlers/stats.py src/bot/__main__.py tests/unit/test_stats_handlers.py
git commit -m "feat: /stats command — personal stats, admin-gated global via /stats all"
```

---

### Task 6: `/top` handler + registration

**Files:**
- Modify: `src/bot/handlers/stats.py`, `src/bot/__main__.py`
- Test: `tests/unit/test_stats_handlers.py`

**Interfaces:**
- Consumes: `StatsService.top_tags/top_creators/top_videos_for_tag` + `TagVideo` (Task 3), locale keys (Task 4), `_ranked` (Task 5).
- Produces: `async handle_top(update, context)` registered for `/top`.

- [ ] **Step 1: Write the failing tests** — append to `tests/unit/test_stats_handlers.py` (extend the existing imports with `handle_top` and `TagVideo`):

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd src && uv run pytest ../tests/unit/test_stats_handlers.py -v -k TestTop`
Expected: FAIL — `ImportError: cannot import name 'handle_top'`

- [ ] **Step 3: Implement** — append to `src/bot/handlers/stats.py`:

```python
async def handle_top(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_user:
        return
    lang = update.effective_user.language_code
    stats: StatsService = context.bot_data["stats"]
    if not stats.enabled:
        await update.effective_message.reply_text(get_message("stats_unavailable", lang))
        return
    arg = context.args[0].lower() if context.args else ""
    try:
        if arg == "tags":
            rows = await stats.top_tags(10)
            if rows:
                items = "\n".join(f"{i}. #{name} — {n}" for i, (name, n) in enumerate(rows, 1))
                text = get_message("top_tags_title", lang, items=items)
            else:
                text = get_message("top_empty", lang)
        elif arg == "creators":
            rows = await stats.top_creators(10)
            if rows:
                text = get_message("top_creators_title", lang, items=_ranked(rows))
            else:
                text = get_message("top_empty", lang)
        elif arg.startswith("#") and len(arg) > 1:
            tag = arg[1:]
            videos = await stats.top_videos_for_tag(tag, 5)
            if videos:
                items = "\n".join(
                    f"{i}. {v.title or '?'} — {v.creator}, "
                    f"❤ {v.like_count if v.like_count is not None else '?'}\n{v.url}"
                    for i, v in enumerate(videos, 1)
                )
                text = get_message("top_videos_title", lang, tag=tag, items=items)
            else:
                text = get_message("top_empty", lang)
        else:
            text = get_message("top_usage", lang)
    except Exception:
        log.warning("stats.query_failed", exc_info=True)
        text = get_message("stats_unavailable", lang)
    await update.effective_message.reply_text(text)
```

Wire into `src/bot/__main__.py`: extend the stats import to `from bot.handlers.stats import handle_stats, handle_top` and register next to `/stats`:

```python
    app.add_handler(CommandHandler("top", handle_top, filters=private & whitelist))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd src && uv run pytest ../tests/unit/test_stats_handlers.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/bot/handlers/stats.py src/bot/__main__.py tests/unit/test_stats_handlers.py
git commit -m "feat: /top command — tags, creators, and top videos per hashtag"
```

---

### Task 7: Full suite + lint + push (bot deploy gate)

**Files:**
- No new files. Possibly small fixes if lint/tests surface issues.

**Interfaces:**
- Consumes: everything from Tasks 1–6.
- Produces: bot `master` pushed to GitHub — the precondition for Task 10's `make deploy-bot`.

- [ ] **Step 1: Run the full test suite**

Run: `cd src && uv run pytest`
Expected: all tests pass (pre-existing + ~35 new)

- [ ] **Step 2: Run lint**

Run: `cd src && uv run ruff check .`
Expected: no findings. Fix anything reported (line length 100) and re-run.

- [ ] **Step 3: Push**

```bash
git push origin master
```

Expected: push succeeds. (`make deploy-bot` pulls from GitHub on the server — nothing deploys yet.)

---

### Task 8: Monitoring repo — postgres datasource + dashboard JSON

**Files:**
- Create: `~/petprojects/monitoring/grafana/provisioning/datasources/tiktokbot.yml`
- Create: `~/petprojects/monitoring/grafana/dashboards/tiktok-bot-analytics.json`

**Interfaces:**
- Consumes: role `tiktokbot_ro` (created live in Task 10), env var `TIKTOKBOT_RO_PASSWORD` from the server-side `/home/abilay/monitoring/.env` (grafana's compose already has `env_file: [.env]` — no compose change).
- Produces: datasource uid `tiktokbot` referenced by every dashboard panel; dashboard uid `tiktok-bot`. Deployed in Task 10.

- [ ] **Step 1: Create the datasource** — `grafana/provisioning/datasources/tiktokbot.yml`:

```yaml
apiVersion: 1
datasources:
  - name: TikTok Bot DB
    type: postgres
    uid: tiktokbot
    access: proxy
    url: postgres:5432
    user: tiktokbot_ro
    editable: false
    secureJsonData:
      password: $TIKTOKBOT_RO_PASSWORD
    jsonData:
      database: tiktokbot
      sslmode: disable
      maxOpenConns: 2
      postgresVersion: 1600
```

- [ ] **Step 2: Create the dashboard** — `grafana/dashboards/tiktok-bot-analytics.json`. Complete file (12 query panels + 4 row headers; every panel targets `{"type": "postgres", "uid": "tiktokbot"}`):

```json
{
  "uid": "tiktok-bot",
  "title": "TikTok Bot Analytics",
  "tags": ["bot", "analytics"],
  "timezone": "browser",
  "schemaVersion": 39,
  "version": 1,
  "refresh": "",
  "time": { "from": "now-30d", "to": "now" },
  "panels": [
    { "type": "row", "title": "Usage & errors", "gridPos": { "h": 1, "w": 24, "x": 0, "y": 0 }, "collapsed": false, "panels": [] },
    {
      "type": "timeseries", "title": "Requests by status",
      "datasource": { "type": "postgres", "uid": "tiktokbot" },
      "gridPos": { "h": 8, "w": 12, "x": 0, "y": 1 },
      "fieldConfig": { "defaults": { "custom": { "stacking": { "mode": "normal" } } }, "overrides": [] },
      "targets": [ { "refId": "A", "format": "time_series", "rawQuery": true, "rawSql": "SELECT $__timeGroup(ts, '1d') AS time, status AS metric, count(*) AS value FROM download_events WHERE $__timeFilter(ts) GROUP BY 1, 2 ORDER BY 1" } ]
    },
    {
      "type": "stat", "title": "Error rate",
      "datasource": { "type": "postgres", "uid": "tiktokbot" },
      "gridPos": { "h": 8, "w": 12, "x": 12, "y": 1 },
      "fieldConfig": { "defaults": { "unit": "percent", "decimals": 1 }, "overrides": [] },
      "targets": [ { "refId": "A", "format": "table", "rawQuery": true, "rawSql": "SELECT round(100.0 * count(*) FILTER (WHERE status <> 'ok') / greatest(count(*), 1), 1) AS error_pct FROM download_events WHERE $__timeFilter(ts)" } ]
    },
    {
      "type": "timeseries", "title": "Requests by platform",
      "datasource": { "type": "postgres", "uid": "tiktokbot" },
      "gridPos": { "h": 8, "w": 12, "x": 0, "y": 9 },
      "fieldConfig": { "defaults": {}, "overrides": [] },
      "targets": [ { "refId": "A", "format": "time_series", "rawQuery": true, "rawSql": "SELECT $__timeGroup(ts, '1d') AS time, platform AS metric, count(*) AS value FROM download_events WHERE $__timeFilter(ts) GROUP BY 1, 2 ORDER BY 1" } ]
    },
    {
      "type": "timeseries", "title": "Requests by output format",
      "datasource": { "type": "postgres", "uid": "tiktokbot" },
      "gridPos": { "h": 8, "w": 12, "x": 12, "y": 9 },
      "fieldConfig": { "defaults": {}, "overrides": [] },
      "targets": [ { "refId": "A", "format": "time_series", "rawQuery": true, "rawSql": "SELECT $__timeGroup(ts, '1d') AS time, output_format AS metric, count(*) AS value FROM download_events WHERE $__timeFilter(ts) GROUP BY 1, 2 ORDER BY 1" } ]
    },
    {
      "type": "timeseries", "title": "Requests by chat type",
      "datasource": { "type": "postgres", "uid": "tiktokbot" },
      "gridPos": { "h": 8, "w": 12, "x": 0, "y": 17 },
      "fieldConfig": { "defaults": {}, "overrides": [] },
      "targets": [ { "refId": "A", "format": "time_series", "rawQuery": true, "rawSql": "SELECT $__timeGroup(ts, '1d') AS time, chat_type AS metric, count(*) AS value FROM download_events WHERE $__timeFilter(ts) GROUP BY 1, 2 ORDER BY 1" } ]
    },
    { "type": "row", "title": "Content tops", "gridPos": { "h": 1, "w": 24, "x": 0, "y": 25 }, "collapsed": false, "panels": [] },
    {
      "type": "table", "title": "Top hashtags",
      "datasource": { "type": "postgres", "uid": "tiktokbot" },
      "gridPos": { "h": 9, "w": 8, "x": 0, "y": 26 },
      "fieldConfig": { "defaults": {}, "overrides": [] },
      "targets": [ { "refId": "A", "format": "table", "rawQuery": true, "rawSql": "SELECT tag AS hashtag, count(*) AS downloads FROM download_events e JOIN videos v ON v.platform = e.platform AND v.video_id = e.video_id CROSS JOIN LATERAL unnest(v.hashtags) AS tag WHERE $__timeFilter(e.ts) AND e.status = 'ok' GROUP BY tag ORDER BY downloads DESC LIMIT 20" } ]
    },
    {
      "type": "table", "title": "Top creators",
      "datasource": { "type": "postgres", "uid": "tiktokbot" },
      "gridPos": { "h": 9, "w": 8, "x": 8, "y": 26 },
      "fieldConfig": { "defaults": {}, "overrides": [] },
      "targets": [ { "refId": "A", "format": "table", "rawQuery": true, "rawSql": "SELECT coalesce(v.author_handle, v.author_name, 'unknown') AS creator, count(*) AS downloads FROM download_events e JOIN videos v ON v.platform = e.platform AND v.video_id = e.video_id WHERE $__timeFilter(e.ts) AND e.status = 'ok' GROUP BY 1 ORDER BY downloads DESC LIMIT 20" } ]
    },
    {
      "type": "table", "title": "Top videos by likes",
      "datasource": { "type": "postgres", "uid": "tiktokbot" },
      "gridPos": { "h": 9, "w": 8, "x": 16, "y": 26 },
      "fieldConfig": { "defaults": {}, "overrides": [] },
      "targets": [ { "refId": "A", "format": "table", "rawQuery": true, "rawSql": "SELECT v.title, coalesce(v.author_handle, v.author_name, 'unknown') AS creator, v.like_count, v.url FROM (SELECT DISTINCT e.platform, e.video_id FROM download_events e WHERE $__timeFilter(e.ts) AND e.status = 'ok') d JOIN videos v ON v.platform = d.platform AND v.video_id = d.video_id ORDER BY v.like_count DESC NULLS LAST LIMIT 20" } ]
    },
    { "type": "row", "title": "Users", "gridPos": { "h": 1, "w": 24, "x": 0, "y": 35 }, "collapsed": false, "panels": [] },
    {
      "type": "table", "title": "Requests per user",
      "datasource": { "type": "postgres", "uid": "tiktokbot" },
      "gridPos": { "h": 8, "w": 12, "x": 0, "y": 36 },
      "fieldConfig": { "defaults": {}, "overrides": [] },
      "targets": [ { "refId": "A", "format": "table", "rawQuery": true, "rawSql": "SELECT user_id::text AS \"user\", count(*) AS requests, count(*) FILTER (WHERE status = 'ok') AS downloads FROM download_events WHERE $__timeFilter(ts) GROUP BY user_id ORDER BY requests DESC" } ]
    },
    {
      "type": "timeseries", "title": "Active users per week",
      "datasource": { "type": "postgres", "uid": "tiktokbot" },
      "gridPos": { "h": 8, "w": 12, "x": 12, "y": 36 },
      "fieldConfig": { "defaults": {}, "overrides": [] },
      "targets": [ { "refId": "A", "format": "time_series", "rawQuery": true, "rawSql": "SELECT $__timeGroup(ts, '7d') AS time, count(DISTINCT user_id) AS value FROM download_events WHERE $__timeFilter(ts) GROUP BY 1 ORDER BY 1" } ]
    },
    { "type": "row", "title": "Performance", "gridPos": { "h": 1, "w": 24, "x": 0, "y": 44 }, "collapsed": false, "panels": [] },
    {
      "type": "table", "title": "Processing time by platform (ms)",
      "datasource": { "type": "postgres", "uid": "tiktokbot" },
      "gridPos": { "h": 8, "w": 12, "x": 0, "y": 45 },
      "fieldConfig": { "defaults": {}, "overrides": [] },
      "targets": [ { "refId": "A", "format": "table", "rawQuery": true, "rawSql": "SELECT platform, round(percentile_cont(0.5) WITHIN GROUP (ORDER BY duration_ms)) AS p50_ms, round(percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms)) AS p95_ms, count(*) AS n FROM download_events WHERE $__timeFilter(ts) AND duration_ms IS NOT NULL GROUP BY platform ORDER BY n DESC" } ]
    },
    {
      "type": "table", "title": "File size by platform",
      "datasource": { "type": "postgres", "uid": "tiktokbot" },
      "gridPos": { "h": 8, "w": 12, "x": 12, "y": 45 },
      "fieldConfig": { "defaults": {}, "overrides": [] },
      "targets": [ { "refId": "A", "format": "table", "rawQuery": true, "rawSql": "SELECT platform, pg_size_pretty(avg(file_size_bytes)::bigint) AS avg_size, pg_size_pretty(max(file_size_bytes)) AS max_size, count(*) AS n FROM download_events WHERE $__timeFilter(ts) AND file_size_bytes IS NOT NULL GROUP BY platform ORDER BY n DESC" } ]
    }
  ]
}
```

- [ ] **Step 3: Validate the JSON parses**

Run: `python3 -m json.tool ~/petprojects/monitoring/grafana/dashboards/tiktok-bot-analytics.json > /dev/null && echo OK`
Expected: `OK`

- [ ] **Step 4: Commit (monitoring repo)**

```bash
cd ~/petprojects/monitoring
git add grafana/provisioning/datasources/tiktokbot.yml grafana/dashboards/tiktok-bot-analytics.json
git commit -m "feat: tiktokbot postgres datasource + bot analytics dashboard"
```

---

### Task 9: Postgres repo — initdb parity for `tiktokbot_ro`

**Files:**
- Create: `~/petprojects/postgres/initdb/02-tiktokbot-ro.sh`
- Modify: `~/petprojects/postgres/docker-compose.yml` (environment block)

**Interfaces:**
- Consumes: nothing (pure fresh-volume parity; the live role is created in Task 10).
- Produces: a fresh postgres volume would recreate `tiktokbot_ro` automatically. **Committed only — do NOT run `make deploy-postgres`** (recreates the shared DB container; owner-timed).

- [ ] **Step 1: Create `initdb/02-tiktokbot-ro.sh`** (mirror the style of `01-apps.sh`):

```bash
#!/bin/bash
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
  CREATE ROLE tiktokbot_ro LOGIN PASSWORD '${TIKTOKBOT_RO_PASSWORD}';
  GRANT CONNECT ON DATABASE tiktokbot TO tiktokbot_ro;
EOSQL
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname tiktokbot <<-EOSQL
  GRANT USAGE ON SCHEMA public TO tiktokbot_ro;
  GRANT SELECT ON ALL TABLES IN SCHEMA public TO tiktokbot_ro;
  ALTER DEFAULT PRIVILEGES FOR ROLE tiktokbot IN SCHEMA public
      GRANT SELECT ON TABLES TO tiktokbot_ro;
EOSQL
```

Then: `chmod +x ~/petprojects/postgres/initdb/02-tiktokbot-ro.sh`

- [ ] **Step 2: Add the env var** to the `environment:` block of `~/petprojects/postgres/docker-compose.yml`, after `TIKTOKBOT_DB_PASSWORD`:

```yaml
      TIKTOKBOT_RO_PASSWORD: ${TIKTOKBOT_RO_PASSWORD}
```

- [ ] **Step 3: Commit (postgres repo) — no deploy**

```bash
cd ~/petprojects/postgres
git add initdb/02-tiktokbot-ro.sh docker-compose.yml
git commit -m "feat: tiktokbot_ro read-only role for Grafana (fresh-volume parity)"
```

Note: the server-side `/home/abilay/postgres/.env` also needs `TIKTOKBOT_RO_PASSWORD=` added **whenever the owner next touches postgres** — record this in Task 11's docs update; it is not needed for anything to work now.

---

### Task 10: Server rollout — role, secret, deploy monitoring

**Files:** none local (server state + `make` targets). Requires Tasks 7, 8 done.

**Interfaces:**
- Consumes: datasource + dashboard from Task 8 (rsynced by `deploy-monitoring`), `01-apps.sh`-created `tiktokbot` DB (already live).
- Produces: live `tiktokbot_ro` role; `TIKTOKBOT_RO_PASSWORD` in `/home/abilay/monitoring/.env`; Grafana serving the dashboard with a healthy datasource.

- [ ] **Step 1: Create the role and store the secret** (single idempotency check first — `CREATE ROLE` fails if it exists, which means a previous run partially completed; investigate before re-running):

```bash
ssh hetzner-deploy bash -s <<'REMOTE'
set -e
PW=$(openssl rand -base64 24 | tr -d '\n')
docker exec postgres psql -U postgres -v ON_ERROR_STOP=1 \
  -c "CREATE ROLE tiktokbot_ro LOGIN PASSWORD '$PW';" \
  -c "GRANT CONNECT ON DATABASE tiktokbot TO tiktokbot_ro;"
docker exec postgres psql -U postgres -d tiktokbot -v ON_ERROR_STOP=1 \
  -c "GRANT USAGE ON SCHEMA public TO tiktokbot_ro;" \
  -c "GRANT SELECT ON ALL TABLES IN SCHEMA public TO tiktokbot_ro;" \
  -c "ALTER DEFAULT PRIVILEGES FOR ROLE tiktokbot IN SCHEMA public GRANT SELECT ON TABLES TO tiktokbot_ro;"
printf 'TIKTOKBOT_RO_PASSWORD=%s\n' "$PW" >> /home/abilay/monitoring/.env
chmod 600 /home/abilay/monitoring/.env
echo "OK: role created, secret stored"
REMOTE
```

Expected: `CREATE ROLE`, `GRANT`, `GRANT`, `GRANT`, `ALTER DEFAULT PRIVILEGES`, `OK: role created, secret stored`

- [ ] **Step 2: Verify the role can read but not write** (TCP forces password auth):

```bash
ssh hetzner-deploy bash -s <<'REMOTE'
set -e
PW=$(grep '^TIKTOKBOT_RO_PASSWORD=' /home/abilay/monitoring/.env | cut -d= -f2-)
docker exec -e PGPASSWORD="$PW" postgres \
  psql -h 127.0.0.1 -U tiktokbot_ro -d tiktokbot -c "SELECT count(*) FROM download_events;"
docker exec -e PGPASSWORD="$PW" postgres \
  psql -h 127.0.0.1 -U tiktokbot_ro -d tiktokbot \
  -c "INSERT INTO download_events (user_id, chat_type, platform, url, output_format, status) VALUES (0,'x','x','x','x','x');" \
  && echo "FAIL: insert should have been denied" || echo "OK: read-only confirmed"
REMOTE
```

Expected: a count row, then `ERROR:  permission denied for table download_events` followed by `OK: read-only confirmed`

- [ ] **Step 3: Deploy monitoring**

```bash
make -C ~/petprojects deploy-monitoring
```

Expected: rsync of the two new grafana files, `docker compose up -d` recreates grafana (config mount changed → `docker compose up -d --force-recreate grafana` if it doesn't pick up: provisioning files are read at startup).

Note: `deploy-monitoring` runs plain `up -d`; since only mounted file *contents* changed, compose may consider grafana unchanged. If so, follow with:

```bash
ssh hetzner-deploy 'cd /home/abilay/monitoring && docker compose restart grafana'
```

- [ ] **Step 4: Verify datasource health and dashboard presence** (auth-proxy header trick from the vault note):

```bash
ssh hetzner-deploy 'docker exec grafana wget -qO- --header="Remote-User: askar" http://127.0.0.1:3000/api/datasources/uid/tiktokbot/health'
ssh hetzner-deploy 'docker exec grafana wget -qO- --header="Remote-User: askar" http://127.0.0.1:3000/api/dashboards/uid/tiktok-bot | head -c 300'
```

Expected: first returns `{"message":"Database Connection OK","status":"OK"}`; second returns dashboard JSON (not a 404). Also check `docker logs --tail 30 grafana` for provisioning errors.

---

### Task 11: Deploy bot + docs closeout

**Files:**
- Modify: `~/petprojects/docs/monitoring-follow-ups.md` (section 2)
- Modify: `~/petprojects/tiktok-tg-bot/CLAUDE.md` (Recent Changes)

Requires Tasks 7, 10 done.

- [ ] **Step 1: Deploy the bot**

```bash
make -C ~/petprojects deploy-bot
```

Expected: server-side `git pull` + rebuild + `up -d` succeeds.

- [ ] **Step 2: Verify startup**

```bash
ssh hetzner-deploy 'docker ps --format "{{.Names}}\t{{.Status}}" | grep -i tiktok'
ssh hetzner-deploy 'docker logs --tail 20 $(docker ps --format "{{.Names}}" | grep -i "tiktok.*bot\|tg-bot" | head -1)'
```

Expected: container Up (healthy/recent), log line `bot.starting` with `analytics_enabled=True`, no tracebacks.

- [ ] **Step 3: Owner smoke test (manual, flag for the user):** in Telegram — `/help` (shows new commands), `/stats`, `/stats all`, `/top`, `/top tags`, `/top creators`, `/top #<some-tag-from-dashboard>`. Data is 1 day old — tiny numbers are correct behavior.

- [ ] **Step 4: Close out docs**

In `~/petprojects/docs/monitoring-follow-ups.md`, replace section 2's body with a done note:

```markdown
## 2. Sub-project C — bot analytics dashboards + `/stats` `/top` — DONE 2026-07-20

Shipped: postgres datasource (uid `tiktokbot`, read-only role `tiktokbot_ro`),
provisioned dashboard `tiktok-bot-analytics.json`, `/stats` (+ admin `/stats all`)
and `/top tags|creators|#tag` in the bot. Spec:
`tiktok-tg-bot/docs/superpowers/specs/2026-07-20-analytics-surfaces-design.md`.
Pending ride-along: add `TIKTOKBOT_RO_PASSWORD` to server `/home/abilay/postgres/.env`
next time postgres is touched (initdb parity only — nothing breaks without it).
```

In `~/petprojects/tiktok-tg-bot/CLAUDE.md` under `## Recent Changes`, prepend:

```markdown
- 004-analytics-surfaces: /stats + /top commands (StatsService reads via shared asyncpg pool), Grafana bot dashboard + tiktokbot datasource
```

Also add `│   └── stats.py` under handlers and `    └── stats.py` note under services in the CLAUDE.md project tree if quick; skip if the tree drifts from reality elsewhere.

- [ ] **Step 5: Commit + push docs (bot repo only — petprojects/docs is not a git repo)**

```bash
cd ~/petprojects/tiktok-tg-bot
git add CLAUDE.md
git commit -m "docs: note analytics surfaces in CLAUDE.md"
git push origin master
```
