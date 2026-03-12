import time
from uuid import uuid4

import structlog
from telegram import Update
from telegram.ext import ContextTypes

from bot.handlers.common import process_request
from bot.locales.messages import get_message
from bot.services.url_parser import extract_url

log = structlog.get_logger()


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

        await process_request(message, text, lang, context)
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
