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
HAVING count(*) FILTER (WHERE status = 'ok') > 0
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


@dataclass
class TagVideo:
    title: str | None
    creator: str
    like_count: int | None
    url: str


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
