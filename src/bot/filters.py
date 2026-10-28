import re

from telegram import Message
from telegram.ext.filters import MessageFilter

from bot.services.user_store import UserStore


class WhitelistFilter(MessageFilter):
    """Passes messages from whitelisted users."""

    def __init__(self, user_store: UserStore) -> None:
        super().__init__()
        self._store = user_store

    def filter(self, message: Message) -> bool:
        if not message.from_user:
            return False
        return self._store.is_allowed(message.from_user.id)


class NonWhitelistFilter(MessageFilter):
    """Passes messages from non-whitelisted users (for request-access flow)."""

    def __init__(self, user_store: UserStore) -> None:
        super().__init__()
        self._store = user_store

    def filter(self, message: Message) -> bool:
        if not message.from_user:
            return False
        return not self._store.is_allowed(message.from_user.id)


class AdminFilter(MessageFilter):
    """Passes messages from admin users only."""

    def __init__(self, user_store: UserStore) -> None:
        super().__init__()
        self._store = user_store

    def filter(self, message: Message) -> bool:
        if not message.from_user:
            return False
        return self._store.is_admin(message.from_user.id)


# Bot messages to admins name the user as "(<telegram id>)"; replying to one targets that user.
_RELAY_ID = re.compile(r"\((\d{5,})\)")


def relay_target(message: Message) -> int | None:
    """User id an admin's reply is addressed to, read from the bot message it replies to."""
    replied = message.reply_to_message
    if not replied or not replied.from_user or not replied.from_user.is_bot or not replied.text:
        return None
    match = _RELAY_ID.search(replied.text)
    return int(match.group(1)) if match else None


class RelayReplyFilter(MessageFilter):
    """Passes replies to bot messages that name a user."""

    def filter(self, message: Message) -> bool:
        return relay_target(message) is not None
