import os

import structlog
from telegram import InputMediaPhoto, Message
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from bot.config import Settings
from bot.locales.messages import get_message
from bot.models.request import OutputFormat
from bot.services.downloader import (
    ErrorType,
    SlideshowResult,
    VideoDownloadError,
    download_audio,
    download_slideshow,
    download_video,
    extract_metadata,
)
from bot.services.format_parser import parse_output_format
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
    ErrorType.NO_AUDIO: "error_no_audio",
}


async def _send_slideshow(
    message: Message, slideshow: SlideshowResult, *, reply_to: int | None = None
) -> None:
    """Send slideshow images as media group(s) and audio if available."""
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

    if slideshow.audio_path and os.path.exists(slideshow.audio_path):
        with open(slideshow.audio_path, "rb") as audio_file:
            await message.reply_audio(
                audio=audio_file,
                title=slideshow.title,
                reply_to_message_id=reply_to,
            )


def _cleanup_slideshow(slideshow: SlideshowResult) -> None:
    for path in slideshow.image_paths:
        if os.path.exists(path):
            os.remove(path)
    if slideshow.audio_path and os.path.exists(slideshow.audio_path):
        os.remove(slideshow.audio_path)


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

    url, _platform = result
    output_format = parse_output_format(text, url)
    log.info("request.format_detected", output_format=output_format.value)

    settings: Settings = context.bot_data["settings"]
    queue: DownloadQueue = context.bot_data["queue"]

    if queue.is_full:
        await message.reply_text(get_message("queued", lang))

    file_path: str | None = None
    slideshow: SlideshowResult | None = None
    try:
        async with queue.acquire():
            metadata = await extract_metadata(url)

            # Validate format compatibility before downloading
            if metadata.duration and metadata.duration > settings.max_duration:
                await message.reply_text(get_message("error_too_long", lang))
                return
            if (
                metadata.file_size
                and metadata.file_size > settings.max_file_size * 1024 * 1024
            ):
                await message.reply_text(get_message("error_too_large", lang))
                return

            if output_format == OutputFormat.IMAGES and not metadata.is_slideshow:
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
                        reply_to_message_id=reply_to,
                    )
                await status_msg.delete()

    except VideoDownloadError as e:
        msg_key = _ERROR_TYPE_TO_MESSAGE_KEY.get(e.error_type, "error_download")
        await message.reply_text(get_message(msg_key, lang))
    except Exception:
        log.exception("request.unhandled_error")
        await message.reply_text(get_message("error_unknown", lang))
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        if slideshow:
            _cleanup_slideshow(slideshow)
