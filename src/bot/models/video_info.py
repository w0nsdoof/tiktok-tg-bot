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
            uploaded_at=(
                datetime.fromtimestamp(timestamp, tz=UTC)
                if timestamp is not None
                else None
            ),
        )
