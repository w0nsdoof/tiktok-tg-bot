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


@pytest.mark.asyncio
async def test_inline_slideshow_records_not_slideshow():
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

    slideshow_metadata = VideoMetadata(
        duration=30, file_size=1000, title="Test", is_slideshow=True, info=VIDEO_INFO
    )
    with (
        patch("bot.handlers.inline.extract_url", return_value=(VIDEO_URL, Platform.TIKTOK)),
        patch("bot.handlers.inline.extract_metadata", return_value=slideshow_metadata),
    ):
        await handle_inline_query(update, ctx)

    event, _ = _recorded_event(ctx)
    assert event.status == "not_slideshow"
    assert event.chat_type == "inline"
    assert event.video_id == "123"


@pytest.mark.asyncio
async def test_inline_missing_file_id_records_download_error():
    from bot.handlers.inline import handle_inline_query

    ctx = _make_context()
    ctx.bot_data["user_store"] = MagicMock()
    ctx.bot_data["user_store"].is_allowed.return_value = True

    sent_message = AsyncMock()
    sent_message.video = None
    ctx.bot.send_video = AsyncMock(return_value=sent_message)

    update = MagicMock()
    query = update.inline_query
    query.from_user.id = 42
    query.from_user.language_code = "en"
    query.query = VIDEO_URL
    query.answer = AsyncMock()

    with (
        patch("bot.handlers.inline.extract_url", return_value=(VIDEO_URL, Platform.TIKTOK)),
        patch("bot.handlers.inline.extract_metadata", return_value=VIDEO_METADATA),
        patch("bot.handlers.inline.download_video", AsyncMock(return_value="/tmp/test/video.mp4")),
        patch("bot.handlers.inline.os.path.getsize", return_value=1000),
        patch("bot.handlers.inline.os.path.exists", return_value=False),
        patch("builtins.open", MagicMock()),
    ):
        await handle_inline_query(update, ctx)

    event, _ = _recorded_event(ctx)
    assert event.status == "download_error"
    assert event.chat_type == "inline"
