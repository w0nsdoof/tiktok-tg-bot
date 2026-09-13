import os
import time

import structlog
from telegram import InputMediaPhoto, InputMediaVideo, Message
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from bot.config import Settings
from bot.locales.messages import get_message
from bot.models.request import OutputFormat
from bot.models.video_info import VideoInfo
from bot.services.analytics import Analytics, DownloadEvent
from bot.services.downloader import (
    ErrorType,
    MediaFile,
    SlideshowResult,
    VideoDownloadError,
    download_audio,
    download_instagram_media,
    download_slideshow,
    download_video,
    extract_metadata,
)
from bot.services.format_parser import parse_output_format
from bot.services.queue import DownloadQueue
from bot.services.url_parser import extract_url
from bot.services.user_store import UserStore

log = structlog.get_logger()

_ERROR_TYPE_TO_MESSAGE_KEY: dict[ErrorType, str] = {
    ErrorType.TOO_LONG: "error_too_long",
    ErrorType.TOO_LARGE: "error_too_large",
    ErrorType.PRIVATE: "error_private",
    ErrorType.AUTH_REQUIRED: "error_auth_required",
    ErrorType.PLATFORM_DOWN: "error_platform_down",
    ErrorType.NOT_VIDEO: "error_not_video",
    ErrorType.DOWNLOAD_ERROR: "error_download",
    ErrorType.NO_AUDIO: "error_no_audio",
}


async def _send_media(
    message: Message, files: list[MediaFile], *, reply_to: int | None = None
) -> None:
    """Send photos/videos as albums of up to 10; Telegram rejects 1-item albums."""
    for batch_start in range(0, len(files), 10):
        batch = files[batch_start : batch_start + 10]
        handles = [open(f.path, "rb") for f in batch]  # noqa: SIM115
        try:
            if len(batch) == 1 and batch[0].is_video:
                await message.reply_video(
                    video=handles[0],
                    supports_streaming=True,
                    reply_to_message_id=reply_to,
                )
            elif len(batch) == 1:
                await message.reply_photo(photo=handles[0], reply_to_message_id=reply_to)
            else:
                media = [
                    InputMediaVideo(media=h, supports_streaming=True)
                    if f.is_video
                    else InputMediaPhoto(media=h)
                    for f, h in zip(batch, handles, strict=True)
                ]
                await message.reply_media_group(
                    media=media,
                    reply_to_message_id=reply_to,
                )
        finally:
            for h in handles:
                h.close()


async def _send_slideshow(
    message: Message, slideshow: SlideshowResult, *, reply_to: int | None = None
) -> None:
    """Send slideshow images as media group(s) and audio if available."""
    await _send_media(
        message,
        [MediaFile(path=p, is_video=False) for p in slideshow.image_paths],
        reply_to=reply_to,
    )

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

    url, platform = result
    output_format = parse_output_format(text, url)
    log.info("request.format_detected", output_format=output_format.value)

    settings: Settings = context.bot_data["settings"]
    queue: DownloadQueue = context.bot_data["queue"]
    analytics: Analytics = context.bot_data["analytics"]
    user_store: UserStore | None = context.bot_data.get("user_store")
    if user_store and message.from_user:
        user_store.observe_identity(
            message.from_user.id,
            username=message.from_user.username,
            display_name=message.from_user.full_name,
        )
    max_duration = (
        user_store.get_runtime_int("max_duration", settings.max_duration)
        if user_store else settings.max_duration
    )
    max_file_size = (
        user_store.get_runtime_int("max_file_size", settings.max_file_size)
        if user_store else settings.max_file_size
    )

    if queue.is_full:
        await message.reply_text(get_message("queued", lang))

    start = time.monotonic()
    status = "ok"
    video_info: VideoInfo | None = None
    sent_file_size: int | None = None
    file_path: str | None = None
    slideshow: SlideshowResult | None = None
    media_files: list[MediaFile] = []
    try:
        async with queue.acquire():
            metadata = await extract_metadata(
                url, cookies_file=settings.instagram_cookies_file
            )
            video_info = metadata.info

            # Validate format compatibility before downloading
            if metadata.duration and metadata.duration > max_duration:
                status = "too_long"
                await message.reply_text(get_message("error_too_long", lang))
                return
            if (
                metadata.file_size
                and metadata.file_size > max_file_size * 1024 * 1024
            ):
                status = "too_large"
                await message.reply_text(get_message("error_too_large", lang))
                return

            photo_items = [item for item in metadata.media_items if not item.is_video]
            if (
                output_format == OutputFormat.IMAGES
                and not metadata.is_slideshow
                and not photo_items
            ):
                status = "not_slideshow"
                await message.reply_text(get_message("error_not_slideshow", lang))
                return

            if output_format == OutputFormat.AUDIO and metadata.media_items:
                status = "no_audio"
                await message.reply_text(get_message("error_no_audio", lang))
                return

            if output_format == OutputFormat.AUDIO:
                # Audio extraction from any content type
                status_msg = await message.reply_text(
                    get_message("downloading_audio", lang)
                )
                await context.bot.send_chat_action(
                    chat_id=message.chat_id, action=ChatAction.UPLOAD_VOICE
                )
                audio_result = await download_audio(
                    url,
                    settings.download_dir,
                    cookies_file=settings.instagram_cookies_file,
                )
                file_path = audio_result.audio_path
                sent_file_size = os.path.getsize(file_path)

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

            elif metadata.media_items:
                status_msg = await message.reply_text(
                    get_message("downloading_photos", lang)
                )
                await context.bot.send_chat_action(
                    chat_id=message.chat_id, action=ChatAction.UPLOAD_PHOTO
                )
                media_files = await download_instagram_media(
                    photo_items
                    if output_format == OutputFormat.IMAGES
                    else metadata.media_items,
                    settings.download_dir,
                    max_file_size * 1024 * 1024,
                )
                sent_file_size = sum(os.path.getsize(f.path) for f in media_files)
                await status_msg.edit_text(get_message("sending_photos", lang))
                await context.bot.send_chat_action(
                    chat_id=message.chat_id, action=ChatAction.UPLOAD_PHOTO
                )
                await _send_media(message, media_files, reply_to=reply_to)
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
                        url,
                        settings.download_dir,
                        include_audio=False,
                        cookies_file=settings.instagram_cookies_file,
                    )
                    await status_msg.edit_text(get_message("sending_photos", lang))
                    await context.bot.send_chat_action(
                        chat_id=message.chat_id, action=ChatAction.UPLOAD_PHOTO
                    )
                    # Send only images (no audio)
                    await _send_media(
                        message,
                        [MediaFile(path=p, is_video=False) for p in slideshow.image_paths],
                        reply_to=reply_to,
                    )
                    await status_msg.delete()
                else:
                    # DEFAULT: images + audio
                    status_msg = await message.reply_text(
                        get_message("downloading_photos", lang)
                    )
                    await context.bot.send_chat_action(
                        chat_id=message.chat_id, action=ChatAction.UPLOAD_PHOTO
                    )
                    slideshow = await download_slideshow(
                        url,
                        settings.download_dir,
                        cookies_file=settings.instagram_cookies_file,
                    )
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

                file_path = await download_video(
                    url,
                    settings.download_dir,
                    cookies_file=settings.instagram_cookies_file,
                )

                actual_size = os.path.getsize(file_path)
                if actual_size > max_file_size * 1024 * 1024:
                    status = "too_large"
                    await status_msg.edit_text(get_message("error_too_large", lang))
                    return
                sent_file_size = actual_size

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
        status = e.error_type.value
        msg_key = _ERROR_TYPE_TO_MESSAGE_KEY.get(e.error_type, "error_download")
        await message.reply_text(get_message(msg_key, lang))
    except Exception:
        status = "unknown_error"
        log.exception("request.unhandled_error")
        await message.reply_text(get_message("error_unknown", lang))
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        if slideshow:
            _cleanup_slideshow(slideshow)
        for media_file in media_files:
            if os.path.exists(media_file.path):
                os.remove(media_file.path)
        user = message.from_user
        analytics.record(
            DownloadEvent(
                user_id=user.id if user else 0,
                chat_type="private" if message.chat.type == "private" else "group",
                platform=platform.value,
                url=url,
                output_format=output_format.value,
                status=status,
                video_id=video_info.video_id if video_info else None,
                duration_ms=int((time.monotonic() - start) * 1000),
                file_size_bytes=sent_file_size,
            ),
            video_info,
        )
