"""Tests for VideoInfo normalization from yt-dlp info dicts."""

from datetime import UTC, datetime

from bot.models.video_info import VideoInfo, extract_hashtags


class TestExtractHashtags:
    def test_from_description(self) -> None:
        assert extract_hashtags("cool vid #fyp #Dance") == ["dance", "fyp"]

    def test_from_tags_list(self) -> None:
        assert extract_hashtags(None, ["Shorts", "gaming"]) == ["gaming", "shorts"]

    def test_merges_and_dedupes(self) -> None:
        assert extract_hashtags("#fyp text", ["FYP", "viral"]) == ["fyp", "viral"]

    def test_empty(self) -> None:
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
    def test_tiktok_mapping(self) -> None:
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

    def test_youtube_mapping(self) -> None:
        v = VideoInfo.from_info_dict(YOUTUBE_INFO, "https://www.youtube.com/shorts/BGQWPY4IigY")
        assert v.platform == "youtube"
        assert v.author_handle == "@somechannel"
        assert v.author_name == "Some Channel"
        assert v.hashtags == ["epic", "shorts"]
        assert v.share_count is None
        assert v.save_count is None

    def test_instagram_mapping(self) -> None:
        v = VideoInfo.from_info_dict(INSTAGRAM_INFO, "https://www.instagram.com/reel/Cxyz123/")
        assert v.platform == "instagram"
        assert v.author_handle == "someuser"
        assert v.author_name == "Some User"
        assert v.duration_s == 12  # float truncated to int
        assert v.view_count is None

    def test_unknown_extractor_and_missing_fields(self) -> None:
        v = VideoInfo.from_info_dict({"id": 42, "extractor": "weird"}, "https://x.test/42")
        assert v.platform == "unknown"
        assert v.video_id == "42"  # coerced to str
        assert v.hashtags == []
        assert v.uploaded_at is None
        assert v.duration_s is None

    def test_unix_epoch_timestamp(self) -> None:
        v = VideoInfo.from_info_dict(
            {"id": "test", "extractor": "test", "timestamp": 0},
            "https://x.test/test",
        )
        assert v.uploaded_at == datetime.fromtimestamp(0, tz=UTC)
