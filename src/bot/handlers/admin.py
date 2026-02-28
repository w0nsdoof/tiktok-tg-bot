import structlog
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MessageOriginHiddenUser,
    MessageOriginUser,
    Update,
)
from telegram.ext import ContextTypes

from bot.locales.messages import get_message
from bot.services.user_store import UserStore

log = structlog.get_logger()


def _get_user_store(context: ContextTypes.DEFAULT_TYPE) -> UserStore:
    return context.bot_data["user_store"]


async def handle_access_denied(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show 'request access' message to non-whitelisted users."""
    if not update.effective_message or not update.effective_user:
        return
    user = update.effective_user
    lang = user.language_code
    user_store = _get_user_store(context)

    if user_store.has_pending_request(user.id):
        await update.effective_message.reply_text(
            get_message("access_already_requested", lang)
        )
        return

    keyboard = [
        [
            InlineKeyboardButton(
                get_message("request_access_button", lang),
                callback_data="request_access",
            )
        ]
    ]
    await update.effective_message.reply_text(
        get_message("access_denied", lang),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def handle_start_denied(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /start from non-whitelisted user."""
    await handle_access_denied(update, context)


async def handle_request_access_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """User pressed 'Request Access' button."""
    query = update.callback_query
    if not query or not query.from_user:
        return
    await query.answer()

    user = query.from_user
    lang = user.language_code
    user_store = _get_user_store(context)

    if user_store.is_allowed(user.id):
        await query.edit_message_text(get_message("access_granted", lang))
        return

    if user_store.has_pending_request(user.id):
        await query.edit_message_text(
            get_message("access_already_requested", lang)
        )
        return

    user_store.add_pending_request(user.id)
    await query.edit_message_text(get_message("access_requested", lang))

    # Notify all admins
    name = user.full_name or "Unknown"
    username = user.username or "none"
    admin_ids = user_store.get_admin_ids()

    keyboard = [
        [
            InlineKeyboardButton(
                get_message("admin_approve_button", lang),
                callback_data=f"access:approve:{user.id}",
            ),
            InlineKeyboardButton(
                get_message("admin_deny_button", lang),
                callback_data=f"access:deny:{user.id}",
            ),
        ]
    ]
    for admin_id in admin_ids:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=get_message(
                    "admin_access_request",
                    lang,
                    name=name,
                    user_id=user.id,
                    username=username,
                ),
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        except Exception:
            log.exception("admin.notify_failed", admin_id=admin_id)


async def handle_access_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Admin pressed Approve or Deny."""
    query = update.callback_query
    if not query or not query.from_user or not query.data:
        return
    await query.answer()

    admin = query.from_user
    lang = admin.language_code
    user_store = _get_user_store(context)

    if not user_store.is_admin(admin.id):
        return

    parts = query.data.split(":")
    action = parts[1]
    target_id = int(parts[2])

    user_store.remove_pending_request(target_id)

    if action == "approve":
        user_store.add_user(target_id, is_admin=False)
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=get_message("access_granted", lang),
            )
        except Exception:
            log.warning("admin.notify_user_failed", user_id=target_id)

        await query.edit_message_text(
            get_message("admin_approved", lang, name="User", user_id=target_id)
        )
    else:
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=get_message("access_rejected", lang),
            )
        except Exception:
            log.warning("admin.notify_user_failed", user_id=target_id)

        await query.edit_message_text(
            get_message("admin_denied", lang, name="User", user_id=target_id)
        )


async def handle_add_forward(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Admin forwarded a message — extract user and add them."""
    if not update.effective_message or not update.effective_user:
        return
    message = update.effective_message
    lang = update.effective_user.language_code
    user_store = _get_user_store(context)

    origin = message.forward_origin
    if origin is None:
        return

    if isinstance(origin, MessageOriginHiddenUser):
        await message.reply_text(get_message("forward_hidden_user", lang))
        return

    if isinstance(origin, MessageOriginUser):
        target_user = origin.sender_user
        target_id = target_user.id
        name = target_user.full_name or str(target_id)

        if user_store.is_allowed(target_id):
            await message.reply_text(
                get_message(
                    "user_already_allowed", lang, name=name, user_id=target_id
                )
            )
            return

        user_store.add_user(target_id, is_admin=False)
        await message.reply_text(
            get_message("user_added", lang, name=name, user_id=target_id)
        )

        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=get_message("access_granted", lang),
            )
        except Exception:
            log.warning("admin.notify_user_failed", user_id=target_id)
        return

    # Other origin types (channel, chat) — not a user we can add
    await message.reply_text(get_message("forward_hidden_user", lang))
