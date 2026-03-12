import time
from uuid import uuid4

import structlog
from telegram import Update
from telegram.ext import ContextTypes

from bot.handlers.common import process_request
from bot.services.url_parser import extract_url

log = structlog.get_logger()


async def handle_group_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not update.effective_message or not update.effective_message.text:
        return

    message = update.effective_message
    user = update.effective_user
    lang = user.language_code if user else None
    text: str = message.text  # type: ignore[assignment]  # guarded by check above

    result = extract_url(text)
    if result is None:
        return  # Silently ignore non-URL messages in groups

    start_time = time.monotonic()
    url, platform = result

    structlog.contextvars.bind_contextvars(
        request_id=str(uuid4()),
        user_id=user.id if user else None,
        chat_id=message.chat_id,
        chat_type="group",
        language=lang,
    )
    log.info("request.received", platform=platform.value, url=url)

    try:
        await process_request(
            message, text, lang, context, reply_to=message.message_id
        )
    finally:
        duration_ms = int((time.monotonic() - start_time) * 1000)
        log.info("request.completed", total_duration_ms=duration_ms)
        structlog.contextvars.unbind_contextvars(
            "request_id", "user_id", "chat_id", "chat_type", "language"
        )
