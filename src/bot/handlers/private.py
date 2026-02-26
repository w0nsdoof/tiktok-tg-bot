import os
import time
from uuid import uuid4

import structlog
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from bot.config import Settings
from bot.locales.messages import get_message
from bot.services.downloader import (
    ErrorType,
    VideoDownloadError,
    download_video,
    extract_metadata,
)
from bot.services.queue import DownloadQueue
from bot.services.url_parser import extract_url

log = structlog.get_logger()

_ERROR_TYPE_TO_MESSAGE_KEY: dict[ErrorType, str] = {
    ErrorType.TOO_LONG: "error_too_long",
    ErrorType.TOO_LARGE: "error_too_large",
    ErrorType.PRIVATE: "error_private",
    ErrorType.PLATFORM_DOWN: "error_platform_down",
    ErrorType.NOT_VIDEO: "error_not_video",
    ErrorType.DOWNLOAD_ERROR: "error_download",
}


async def handle_private_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not update.effective_message or not update.effective_message.text:
        return

    message = update.effective_message
    user = update.effective_user
    lang = user.language_code if user else None
    text: str = message.text  # type: ignore[assignment]  # guarded by check above

    start_time = time.monotonic()
    structlog.contextvars.bind_contextvars(
        request_id=str(uuid4()),
        user_id=user.id if user else None,
        chat_id=message.chat_id,
        chat_type="private",
        language=lang,
    )
    log.info("request.received", text_length=len(text))

    try:
        result = extract_url(text)
        if result is None:
            await message.reply_text(get_message("help", lang))
            return

        url, _platform = result
        settings: Settings = context.bot_data["settings"]
        queue: DownloadQueue = context.bot_data["queue"]

        if queue.is_full:
            await message.reply_text(get_message("queued", lang))

        file_path: str | None = None
        try:
            async with queue.acquire():
                status_msg = await message.reply_text(get_message("downloading", lang))
                await context.bot.send_chat_action(
                    chat_id=message.chat_id, action=ChatAction.UPLOAD_VIDEO
                )

                metadata = await extract_metadata(url)

                if metadata.duration and metadata.duration > settings.max_duration:
                    await status_msg.edit_text(get_message("error_too_long", lang))
                    return

                if (
                    metadata.file_size
                    and metadata.file_size > settings.max_file_size * 1024 * 1024
                ):
                    await status_msg.edit_text(get_message("error_too_large", lang))
                    return

                file_path = await download_video(url, settings.download_dir)

                actual_size = os.path.getsize(file_path)
                if actual_size > settings.max_file_size * 1024 * 1024:
                    await status_msg.edit_text(get_message("error_too_large", lang))
                    return

                await status_msg.edit_text(get_message("sending", lang))
                await context.bot.send_chat_action(
                    chat_id=message.chat_id, action=ChatAction.UPLOAD_VIDEO
                )
                with open(file_path, "rb") as video_file:
                    await message.reply_video(
                        video=video_file,
                        supports_streaming=True,
                    )
                await status_msg.delete()

        except VideoDownloadError as e:
            msg_key = _ERROR_TYPE_TO_MESSAGE_KEY.get(e.error_type, "error_download")
            await message.reply_text(get_message(msg_key, lang))
        except Exception:
            log.exception("private.unhandled_error")
            await message.reply_text(get_message("error_unknown", lang))
        finally:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
    finally:
        duration_ms = int((time.monotonic() - start_time) * 1000)
        log.info("request.completed", total_duration_ms=duration_ms)
        structlog.contextvars.unbind_contextvars(
            "request_id", "user_id", "chat_id", "chat_type", "language"
        )


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message:
        return
    user = update.effective_user
    lang = user.language_code if user else None
    await update.effective_message.reply_text(get_message("help", lang))


async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message:
        return
    user = update.effective_user
    lang = user.language_code if user else None
    await update.effective_message.reply_text(get_message("help", lang))
