import os

import structlog
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    InlineQueryHandler,
    MessageHandler,
    filters,
)

from bot.config import Settings
from bot.filters import AdminFilter, NonWhitelistFilter, WhitelistFilter
from bot.handlers.admin import (
    handle_access_callback,
    handle_access_denied,
    handle_add_forward,
    handle_request_access_callback,
    handle_start_denied,
)
from bot.handlers.group import handle_group_message
from bot.handlers.inline import handle_inline_query
from bot.handlers.private import handle_help, handle_private_message, handle_start
from bot.handlers.stats import handle_stats
from bot.health import heartbeat_job
from bot.logging import setup_logging
from bot.services.analytics import Analytics
from bot.services.stats import StatsService
from bot.services.user_store import UserStore


def main() -> None:
    settings = Settings()  # type: ignore[call-arg]
    setup_logging(settings)
    log = structlog.get_logger()

    os.makedirs(settings.download_dir, exist_ok=True)

    # Initialize user store — merges env seeds into persistent JSON
    user_store = UserStore(
        data_dir=settings.data_dir,
        seed_admin_ids=settings.admin_user_ids,
        seed_user_ids=settings.allowed_user_ids,
    )

    if not user_store.get_admin_ids():
        log.warning(
            "bot.no_admins",
            msg="No admin users configured — nobody can approve access requests",
        )

    analytics = Analytics(
        settings.analytics_dsn.get_secret_value() if settings.analytics_dsn else None
    )

    async def _post_init(app_: object) -> None:
        await analytics.ensure_schema()

    async def _post_shutdown(app_: object) -> None:
        await analytics.close()

    app = (
        Application.builder()
        .token(settings.bot_token.get_secret_value())
        .concurrent_updates(True)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )

    # Store shared state on bot_data for handler access
    from bot.services.queue import DownloadQueue

    app.bot_data["settings"] = settings
    app.bot_data["queue"] = DownloadQueue(settings.max_concurrent_downloads)
    app.bot_data["user_store"] = user_store
    app.bot_data["analytics"] = analytics
    app.bot_data["stats"] = StatsService(analytics)

    # Build dynamic filters
    whitelist = WhitelistFilter(user_store)
    non_whitelist = NonWhitelistFilter(user_store)
    admin = AdminFilter(user_store)
    private = filters.ChatType.PRIVATE

    # --- Callback query handlers ---
    app.add_handler(
        CallbackQueryHandler(handle_access_callback, pattern=r"^access:(approve|deny):\d+$")
    )
    app.add_handler(
        CallbackQueryHandler(handle_request_access_callback, pattern=r"^request_access$")
    )

    # --- Admin: forwarded messages in private chat ---
    app.add_handler(MessageHandler(private & admin & filters.FORWARDED, handle_add_forward))

    # --- Private chat: whitelisted users ---
    app.add_handler(CommandHandler("start", handle_start, filters=private & whitelist))
    app.add_handler(CommandHandler("help", handle_help, filters=private & whitelist))
    app.add_handler(CommandHandler("stats", handle_stats, filters=private & whitelist))
    private_text = filters.TEXT & ~filters.COMMAND
    app.add_handler(
        MessageHandler(private & whitelist & private_text, handle_private_message)
    )

    # --- Private chat: non-whitelisted users (request-access flow) ---
    app.add_handler(CommandHandler("start", handle_start_denied, filters=private & non_whitelist))
    app.add_handler(
        MessageHandler(private & non_whitelist & private_text, handle_access_denied)
    )

    # --- Group chat (open to all members, unchanged) ---
    group_filter = (
        (filters.ChatType.GROUP | filters.ChatType.SUPERGROUP) & filters.TEXT & ~filters.COMMAND
    )
    app.add_handler(MessageHandler(group_filter, handle_group_message))

    # --- Inline query (whitelist checked inside handler) ---
    app.add_handler(InlineQueryHandler(handle_inline_query))

    log.info(
        "bot.starting",
        allowed_users=user_store.user_count,
        admins=user_store.admin_count,
        max_concurrent_downloads=settings.max_concurrent_downloads,
        log_level=settings.log_level,
        analytics_enabled=analytics.enabled,
    )
    assert app.job_queue is not None  # job-queue extra is a hard dependency
    app.job_queue.run_repeating(heartbeat_job, interval=30, first=0)
    app.run_polling()
    log.info("bot.shutdown")


if __name__ == "__main__":
    main()
