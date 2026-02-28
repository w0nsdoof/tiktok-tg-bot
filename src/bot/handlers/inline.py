import os
import time
from uuid import uuid4

import structlog
from telegram import (
    InlineQueryResultArticle,
    InlineQueryResultCachedVideo,
    InputTextMessageContent,
    Update,
)
from telegram._inline.inlinequery import InlineQuery
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from bot.locales.messages import get_message
from bot.services.downloader import (
    ErrorType,
    VideoDownloadError,
    download_video,
    extract_metadata,
)
from bot.services.queue import DownloadQueue
from bot.services.url_parser import extract_url
from bot.services.user_store import UserStore

log = structlog.get_logger()

_ERROR_TYPE_TO_MESSAGE_KEY: dict[ErrorType, str] = {
    ErrorType.TOO_LONG: "error_too_long",
    ErrorType.TOO_LARGE: "error_too_large",
    ErrorType.PRIVATE: "error_private",
    ErrorType.PLATFORM_DOWN: "error_platform_down",
    ErrorType.NOT_VIDEO: "error_not_video",
    ErrorType.DOWNLOAD_ERROR: "error_download",
}


def _error_article(msg_key: str, lang: str | None) -> InlineQueryResultArticle:
    return InlineQueryResultArticle(
        id=str(uuid4()),
        title=get_message(msg_key, lang),
        input_message_content=InputTextMessageContent(
            message_text=get_message(msg_key, lang)
        ),
    )


async def _safe_answer(
    query: InlineQuery,
    results: list[InlineQueryResultArticle | InlineQueryResultCachedVideo],
) -> None:
    """Answer inline query, silently ignoring expired queries."""
    try:
        await query.answer(results, cache_time=0)
    except BadRequest as e:
        if "query is too old" in str(e).lower():
            log.warning("inline.query_expired")
        else:
            raise


async def handle_inline_query(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not update.inline_query:
        return

    query = update.inline_query
    user = query.from_user
    lang = user.language_code if user else None

    user_store: UserStore = context.bot_data["user_store"]

    # Whitelist check for inline mode
    if not user_store.is_allowed(user.id):
        await _safe_answer(query, [])
        return

    settings = context.bot_data["settings"]

    start_time = time.monotonic()
    structlog.contextvars.bind_contextvars(
        request_id=str(uuid4()),
        user_id=user.id,
        chat_type="inline",
        language=lang,
    )
    log.info("request.received", query=query.query)

    text = query.query.strip()
    result = extract_url(text) if text else None

    if result is None:
        help_result = InlineQueryResultArticle(
            id=str(uuid4()),
            title=get_message("help_inline", lang),
            input_message_content=InputTextMessageContent(
                message_text=get_message("help", lang)
            ),
        )
        await _safe_answer(query, [help_result])
        return

    url, _platform = result
    queue: DownloadQueue = context.bot_data["queue"]

    file_path: str | None = None
    try:
        async with queue.acquire():
            metadata = await extract_metadata(url)

            if metadata.is_slideshow:
                await _safe_answer(
                    query, [_error_article("error_slideshow_inline", lang)]
                )
                return

            if metadata.duration and metadata.duration > settings.max_duration:
                await _safe_answer(query, [_error_article("error_too_long", lang)])
                return

            if metadata.file_size and metadata.file_size > settings.max_file_size * 1024 * 1024:
                await _safe_answer(query, [_error_article("error_too_large", lang)])
                return

            file_path = await download_video(url, settings.download_dir)

            actual_size = os.path.getsize(file_path)
            if actual_size > settings.max_file_size * 1024 * 1024:
                await _safe_answer(query, [_error_article("error_too_large", lang)])
                return

            # Upload video to user's DM to get a file_id, then delete the DM message
            with open(file_path, "rb") as video_file:
                sent = await context.bot.send_video(
                    chat_id=user.id,
                    video=video_file,
                    supports_streaming=True,
                    disable_notification=True,
                )
            file_id = sent.video.file_id if sent.video else None
            await sent.delete()

            if not file_id:
                await _safe_answer(query, [_error_article("error_download", lang)])
                return

            video_result = InlineQueryResultCachedVideo(
                id=str(uuid4()),
                video_file_id=file_id,
                title=metadata.title or "Downloaded video",
            )
            await _safe_answer(query, [video_result])

    except VideoDownloadError as e:
        msg_key = _ERROR_TYPE_TO_MESSAGE_KEY.get(e.error_type, "error_download")
        await _safe_answer(query, [_error_article(msg_key, lang)])
    except Exception:
        log.exception("inline.unhandled_error")
        await _safe_answer(query, [_error_article("error_unknown", lang)])
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        duration_ms = int((time.monotonic() - start_time) * 1000)
        log.info("request.completed", total_duration_ms=duration_ms)
        structlog.contextvars.unbind_contextvars(
            "request_id", "user_id", "chat_type", "language"
        )
