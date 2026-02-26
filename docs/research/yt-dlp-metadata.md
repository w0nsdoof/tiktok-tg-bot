# yt-dlp Metadata Fields by Platform

**Date**: 2026-02-24

## Overview

yt-dlp's `extract_info(url, download=False)` returns a rich info dict. Available fields vary by platform. This document catalogs what's available for our three supported platforms.

## TikTok

| Field | Type | Description |
|-------|------|-------------|
| `id` | str | Numeric video ID |
| `title` | str | Description truncated to 72 chars |
| `description` | str | Full caption (includes hashtags as `#tag` text) |
| `timestamp` | int | UNIX upload timestamp |
| `duration` | int | Video length in seconds |
| `view_count` | int | Play count |
| `like_count` | int | Likes |
| `comment_count` | int | Comments |
| `repost_count` | int | Shares |
| `save_count` | int | Bookmarks/favorites |
| `uploader` | str | Username handle (unique_id) |
| `channel` | str | Display name / nickname |
| `uploader_url` | str | Profile URL |
| `track` | str | Sound/music title |
| `album` | str | Album name |
| `artists` | list[str] | Music author(s) |
| `thumbnails` | list[dict] | Multiple cover images (cover, origin, dynamic, animated) |
| `thumbnail` | str | Best thumbnail URL |
| `availability` | str | "private", "public", etc. |
| `subtitles` | dict | Available captions |

**Notes:**
- No `tags` field. Hashtags must be parsed from `description` via `re.findall(r'#(\w+)', desc)`.
- Every TikTok has a sound, so `track`/`artists` is always populated.
- Richest engagement metrics of all three platforms.

## YouTube Shorts

Uses the same extractor as regular YouTube videos. Shorts are identified by `media_type: "short"`.

| Field | Type | Description |
|-------|------|-------------|
| `id` | str | Video ID (e.g. "BGQWPY4IigY") |
| `title` | str | Full video title |
| `description` | str | Full description |
| `tags` | list[str] | Video tags as proper list |
| `categories` | list[str] | Content category (e.g. "People & Blogs") |
| `timestamp` | int | UNIX upload timestamp |
| `duration` | int | Video length in seconds |
| `view_count` | int | Views |
| `like_count` | int | Likes |
| `comment_count` | int | Comments |
| `uploader` | str | Channel name |
| `uploader_id` | str | Channel handle (e.g. "@PhilippHagemeister") |
| `uploader_url` | str | Channel URL |
| `channel` | str | Channel name |
| `channel_id` | str | Channel ID |
| `channel_follower_count` | int | Subscriber count |
| `channel_is_verified` | bool | Verification badge |
| `media_type` | str | "short" for Shorts |
| `thumbnails` | list[dict] | Many resolution variants |
| `thumbnail` | str | Best thumbnail URL |
| `age_limit` | int | 0 = none, 18 = restricted |
| `availability` | str | "public", "private", "unlisted", etc. |
| `track` | str | Music title (music videos only) |
| `artists` | list[str] | Artists (music videos only) |
| `subtitles` | dict | Available captions |
| `automatic_captions` | dict | Auto-generated captions |

**Notes:**
- Only platform with a proper `tags` list.
- Most metadata overall: categories, subscriber count, verification.
- `media_type: "short"` distinguishes Shorts from regular videos.

## Instagram Reels

| Field | Type | Description |
|-------|------|-------------|
| `id` | str | Post shortcode |
| `title` | str | Post title or "Video by {username}" |
| `description` | str | Full caption text |
| `timestamp` | int | UNIX upload timestamp |
| `duration` | float | Length in seconds (sub-second precision) |
| `view_count` | int | Views (API path only) |
| `like_count` | int | Likes |
| `comment_count` | int | Comments |
| `comments` | list[dict] | Inline comment objects (author, text, timestamp) |
| `uploader` | str | User's display name |
| `uploader_id` | str | Numeric user ID |
| `channel` | str | Username handle |
| `thumbnails` | list[dict] | Multiple resolutions |
| `thumbnail` | str | Best thumbnail URL |

**Notes:**
- No `tags` field. Hashtags in `description`, same as TikTok.
- No music metadata.
- No `uploader_url` or `channel_url`.
- Most restrictive — many fields require session cookie authentication.
- `duration` is float, not int.

## Cross-Platform Comparison

| Field | TikTok | YouTube | Instagram |
|-------|--------|---------|-----------|
| title | truncated desc | full title | auto or caption |
| description | full caption | full desc | full caption |
| hashtags | parse desc | `tags` list | parse desc |
| author handle | `uploader` | `uploader_id` | `channel` |
| author name | `channel` | `uploader` | `uploader` |
| view_count | yes | yes | needs auth |
| like_count | yes | yes | yes |
| comment_count | yes | yes | yes |
| share_count | yes | no | no |
| save_count | yes | no | no |
| music info | always | music videos | no |
| subscriber count | no | yes | no |
| verified badge | no | yes | no |

## Proposed Normalized Model

```python
@dataclass
class VideoInfo:
    video_id: str
    url: str
    platform: Platform

    title: str | None
    description: str | None
    hashtags: list[str]
    thumbnail_url: str | None

    author_handle: str | None
    author_name: str | None

    duration: int | None
    file_size: int | None

    view_count: int | None
    like_count: int | None
    comment_count: int | None
    share_count: int | None          # TikTok only
    save_count: int | None           # TikTok only

    track: str | None                # TikTok mainly
    artist: str | None

    uploaded_at: datetime | None
```

## Hashtag Extraction

```python
import re

def extract_hashtags(description: str | None, tags: list[str] | None = None) -> list[str]:
    """Extract hashtags from description text and/or tags list."""
    result: set[str] = set()
    if tags:
        result.update(t.lower() for t in tags)
    if description:
        result.update(t.lower() for t in re.findall(r'#(\w+)', description))
    return sorted(result)
```
