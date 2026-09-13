"""Tests for the 6-branch decision matrix in process_request().

Matrix: (DEFAULT/AUDIO/IMAGES) x (video/slideshow)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.locales.messages import get_message
from bot.models.request import OutputFormat
from bot.services.downloader import (
    AudioResult,
    MediaFile,
    MediaItem,
    SlideshowResult,
    VideoMetadata,
)


def _make_context(settings=None):
    """Create a mock context with settings and queue."""
    ctx = MagicMock()
    ctx.bot_data = {
        "settings": settings or MagicMock(
            max_duration=300,
            max_file_size=50,
            download_dir="/tmp/test",
        ),
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
    """Create a mock Telegram message."""
    msg = AsyncMock()
    msg.chat_id = 123
    msg.message_id = 456
    msg.chat.type = "private"
    msg.from_user.id = 111
    msg.reply_text = AsyncMock()
    msg.reply_video = AsyncMock()
    msg.reply_audio = AsyncMock()
    msg.reply_media_group = AsyncMock()

    status_msg = AsyncMock()
    status_msg.edit_text = AsyncMock()
    status_msg.delete = AsyncMock()
    msg.reply_text.return_value = status_msg

    return msg


VIDEO_URL = "https://www.tiktok.com/@user/video/123"
VIDEO_METADATA = VideoMetadata(duration=30, file_size=1000, title="Test Video", is_slideshow=False)
SLIDESHOW_METADATA = VideoMetadata(
    duration=10, file_size=500, title="Test Slideshow", is_slideshow=True
)


class TestDefaultVideo:
    """DEFAULT format + video content -> download video, send as MP4."""

    @pytest.mark.asyncio
    async def test_downloads_and_sends_video(self, tmp_path):
        video_file = tmp_path / "video.mp4"
        video_file.write_bytes(b"fake video")

        msg = _make_message()
        ctx = _make_context()

        with (
            patch("bot.handlers.common.extract_url", return_value=(VIDEO_URL, MagicMock())),
            patch("bot.handlers.common.parse_output_format", return_value=OutputFormat.DEFAULT),
            patch("bot.handlers.common.extract_metadata", return_value=VIDEO_METADATA),
            patch("bot.handlers.common.download_video", return_value=str(video_file)),
        ):
            from bot.handlers.common import process_request
            await process_request(msg, f"{VIDEO_URL}", "en", ctx)

        msg.reply_video.assert_called_once()


class TestDefaultSlideshow:
    """DEFAULT format + slideshow content -> download slideshow, send images + audio."""

    @pytest.mark.asyncio
    async def test_sends_images_and_audio(self, tmp_path):
        img = tmp_path / "img.jpeg"
        img.write_bytes(b"img")
        audio = tmp_path / "audio.m4a"
        audio.write_bytes(b"audio")
        slideshow = SlideshowResult(
            image_paths=[str(img), str(img)], audio_path=str(audio), title="Slide"
        )

        msg = _make_message()
        ctx = _make_context()

        with (
            patch("bot.handlers.common.extract_url", return_value=(VIDEO_URL, MagicMock())),
            patch("bot.handlers.common.parse_output_format", return_value=OutputFormat.DEFAULT),
            patch("bot.handlers.common.extract_metadata", return_value=SLIDESHOW_METADATA),
            patch("bot.handlers.common.download_slideshow", return_value=slideshow),
        ):
            from bot.handlers.common import process_request
            await process_request(msg, f"{VIDEO_URL}", "en", ctx)

        msg.reply_media_group.assert_called_once()
        msg.reply_audio.assert_called_once()


class TestAudioVideo:
    """AUDIO format + video content -> extract audio, send as music player file."""

    @pytest.mark.asyncio
    async def test_sends_audio(self, tmp_path):
        audio_file = tmp_path / "audio.m4a"
        audio_file.write_bytes(b"audio data")
        audio_result = AudioResult(
            audio_path=str(audio_file), title="Test", duration=30
        )

        msg = _make_message()
        ctx = _make_context()

        with (
            patch("bot.handlers.common.extract_url", return_value=(VIDEO_URL, MagicMock())),
            patch("bot.handlers.common.parse_output_format", return_value=OutputFormat.AUDIO),
            patch("bot.handlers.common.extract_metadata", return_value=VIDEO_METADATA),
            patch("bot.handlers.common.download_audio", return_value=audio_result),
        ):
            from bot.handlers.common import process_request
            await process_request(msg, f"audio {VIDEO_URL}", "en", ctx)

        msg.reply_audio.assert_called_once()


class TestAudioSlideshow:
    """AUDIO format + slideshow content -> extract audio only."""

    @pytest.mark.asyncio
    async def test_sends_audio_from_slideshow(self, tmp_path):
        audio_file = tmp_path / "audio.m4a"
        audio_file.write_bytes(b"audio data")
        audio_result = AudioResult(
            audio_path=str(audio_file), title="Slideshow Audio", duration=15
        )

        msg = _make_message()
        ctx = _make_context()

        with (
            patch("bot.handlers.common.extract_url", return_value=(VIDEO_URL, MagicMock())),
            patch("bot.handlers.common.parse_output_format", return_value=OutputFormat.AUDIO),
            patch("bot.handlers.common.extract_metadata", return_value=SLIDESHOW_METADATA),
            patch("bot.handlers.common.download_audio", return_value=audio_result),
        ):
            from bot.handlers.common import process_request
            await process_request(msg, f"audio {VIDEO_URL}", "en", ctx)

        msg.reply_audio.assert_called_once()
        msg.reply_media_group.assert_not_called()


class TestImagesSlideshow:
    """IMAGES format + slideshow content -> send images only, no audio."""

    @pytest.mark.asyncio
    async def test_sends_images_only(self, tmp_path):
        img = tmp_path / "img.jpeg"
        img.write_bytes(b"img")
        slideshow = SlideshowResult(
            image_paths=[str(img), str(img)], audio_path=None, title="Slide"
        )

        msg = _make_message()
        ctx = _make_context()

        with (
            patch("bot.handlers.common.extract_url", return_value=(VIDEO_URL, MagicMock())),
            patch("bot.handlers.common.parse_output_format", return_value=OutputFormat.IMAGES),
            patch("bot.handlers.common.extract_metadata", return_value=SLIDESHOW_METADATA),
            patch("bot.handlers.common.download_slideshow", return_value=slideshow) as mock_dl,
        ):
            from bot.handlers.common import process_request
            await process_request(msg, f"images {VIDEO_URL}", "en", ctx)

        mock_dl.assert_called_once()
        # include_audio=False should be passed
        _, kwargs = mock_dl.call_args
        assert kwargs.get("include_audio") is False
        msg.reply_media_group.assert_called_once()
        msg.reply_audio.assert_not_called()


class TestImagesVideoError:
    """IMAGES format + video content -> error message (incompatible)."""

    @pytest.mark.asyncio
    async def test_returns_error(self):
        msg = _make_message()
        ctx = _make_context()

        with (
            patch("bot.handlers.common.extract_url", return_value=(VIDEO_URL, MagicMock())),
            patch("bot.handlers.common.parse_output_format", return_value=OutputFormat.IMAGES),
            patch("bot.handlers.common.extract_metadata", return_value=VIDEO_METADATA),
        ):
            from bot.handlers.common import process_request
            await process_request(msg, f"images {VIDEO_URL}", "en", ctx)

        # Should send error message, not attempt download
        msg.reply_text.assert_called()
        # The second call (after status message) should contain the error
        error_call = msg.reply_text.call_args_list[-1]
        assert "video" in error_call.args[0].lower() or "slideshow" in error_call.args[0].lower()
        msg.reply_video.assert_not_called()
        msg.reply_media_group.assert_not_called()


class TestSlideshowAlbumSplit:
    """Telegram rejects 1-item albums, so a leftover image is sent on its own."""

    @pytest.mark.asyncio
    async def test_eleven_images_sent_as_album_plus_single_photo(self, tmp_path):
        img = tmp_path / "img.jpeg"
        img.write_bytes(b"img")
        slideshow = SlideshowResult(image_paths=[str(img)] * 11, audio_path=None, title="Slide")

        msg = _make_message()
        ctx = _make_context()

        with (
            patch("bot.handlers.common.extract_url", return_value=(VIDEO_URL, MagicMock())),
            patch("bot.handlers.common.parse_output_format", return_value=OutputFormat.DEFAULT),
            patch("bot.handlers.common.extract_metadata", return_value=SLIDESHOW_METADATA),
            patch("bot.handlers.common.download_slideshow", return_value=slideshow),
        ):
            from bot.handlers.common import process_request
            await process_request(msg, f"{VIDEO_URL}", "en", ctx)

        msg.reply_media_group.assert_called_once()
        assert len(msg.reply_media_group.call_args.kwargs["media"]) == 10
        msg.reply_photo.assert_called_once()


IG_URL = "https://www.instagram.com/p/abc/"


def _ig_metadata(*kinds):
    items = [
        MediaItem(url=f"https://cdn/{i}", is_video=kind == "video")
        for i, kind in enumerate(kinds)
    ]
    return VideoMetadata(duration=None, file_size=None, title="Post", media_items=items)


def _media_files(tmp_path, *kinds):
    files = []
    for i, kind in enumerate(kinds):
        path = tmp_path / f"{i}.{'mp4' if kind == 'video' else 'jpg'}"
        path.write_bytes(b"data")
        files.append(MediaFile(path=str(path), is_video=kind == "video"))
    return files


class TestInstagramMedia:
    """Instagram photo and carousel posts -> photos/videos sent as albums."""

    async def _run(self, text, output_format, metadata, files=None):
        msg = _make_message()
        ctx = _make_context()
        with (
            patch("bot.handlers.common.extract_url", return_value=(IG_URL, MagicMock())),
            patch("bot.handlers.common.parse_output_format", return_value=output_format),
            patch("bot.handlers.common.extract_metadata", return_value=metadata),
            patch(
                "bot.handlers.common.download_instagram_media", return_value=files
            ) as mock_dl,
            patch("bot.handlers.common.download_audio") as mock_audio,
        ):
            from bot.handlers.common import process_request
            await process_request(msg, text, "en", ctx)
        return msg, mock_dl, mock_audio

    @pytest.mark.asyncio
    async def test_single_photo_sent_as_photo(self, tmp_path):
        msg, _, _ = await self._run(
            IG_URL, OutputFormat.DEFAULT, _ig_metadata("photo"), _media_files(tmp_path, "photo")
        )

        msg.reply_photo.assert_called_once()
        msg.reply_media_group.assert_not_called()

    @pytest.mark.asyncio
    async def test_eleven_items_sent_as_album_plus_single(self, tmp_path):
        kinds = ["photo"] * 10 + ["video"]

        msg, _, _ = await self._run(
            IG_URL, OutputFormat.DEFAULT, _ig_metadata(*kinds), _media_files(tmp_path, *kinds)
        )

        msg.reply_media_group.assert_called_once()
        assert len(msg.reply_media_group.call_args.kwargs["media"]) == 10
        msg.reply_video.assert_called_once()

    @pytest.mark.asyncio
    async def test_images_keyword_downloads_only_photos(self, tmp_path):
        _, mock_dl, _ = await self._run(
            f"images {IG_URL}",
            OutputFormat.IMAGES,
            _ig_metadata("photo", "video", "photo"),
            _media_files(tmp_path, "photo", "photo"),
        )

        requested = mock_dl.call_args.args[0]
        assert [item.is_video for item in requested] == [False, False]

    @pytest.mark.asyncio
    async def test_audio_keyword_replies_no_audio(self):
        msg, mock_dl, mock_audio = await self._run(
            f"audio {IG_URL}", OutputFormat.AUDIO, _ig_metadata("photo")
        )

        mock_audio.assert_not_called()
        mock_dl.assert_not_called()
        assert msg.reply_text.call_args.args[0] == get_message("error_no_audio", "en")
