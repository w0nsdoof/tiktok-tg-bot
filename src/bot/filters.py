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
