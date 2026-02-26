import os

import structlog
from telegram.ext import Application, CommandHandler, InlineQueryHandler, MessageHandler, filters

from bot.config import Settings
from bot.handlers.group import handle_group_message
from bot.handlers.inline import handle_inline_query
from bot.handlers.private import handle_help, handle_private_message, handle_start
from bot.logging import setup_logging


def main() -> None:
    settings = Settings()  # type: ignore[call-arg]
    setup_logging(settings)
    log = structlog.get_logger()

    os.makedirs(settings.download_dir, exist_ok=True)

    app = (
        Application.builder()
        .token(settings.bot_token.get_secret_value())
        .concurrent_updates(True)
        .build()
    )

    # Store settings and queue on bot_data for handler access
    from bot.services.queue import DownloadQueue

    app.bot_data["settings"] = settings
    app.bot_data["queue"] = DownloadQueue(settings.max_concurrent_downloads)

    # Private chat handlers (whitelisted users only)
    user_filter = (
        filters.User(user_id=settings.allowed_user_ids)
        if settings.allowed_user_ids
        else filters.ALL
    )
    private_filter = filters.ChatType.PRIVATE & user_filter

    app.add_handler(CommandHandler("start", handle_start, filters=private_filter))
    app.add_handler(CommandHandler("help", handle_help, filters=private_filter))
    app.add_handler(
        MessageHandler(private_filter & filters.TEXT & ~filters.COMMAND, handle_private_message)
    )

    # Group chat handlers (open to all members)
    group_filter = (
        (filters.ChatType.GROUP | filters.ChatType.SUPERGROUP) & filters.TEXT & ~filters.COMMAND
    )
    app.add_handler(MessageHandler(group_filter, handle_group_message))

    # Inline query handler (whitelist checked inside handler)
    app.add_handler(InlineQueryHandler(handle_inline_query))

    log.info(
        "bot.starting",
        allowed_users=len(settings.allowed_user_ids),
        max_concurrent_downloads=settings.max_concurrent_downloads,
        log_level=settings.log_level,
    )
    app.run_polling()
    log.info("bot.shutdown")


if __name__ == "__main__":
    main()
