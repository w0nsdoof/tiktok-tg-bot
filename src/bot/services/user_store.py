import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime

import structlog

log = structlog.get_logger()


@dataclass
class UserRecord:
    user_id: int
    is_admin: bool = False
    added_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class UserStore:
    """In-memory whitelist backed by a JSON file."""

    def __init__(
        self,
        data_dir: str,
        seed_admin_ids: list[int],
        seed_user_ids: list[int],
    ) -> None:
        self._data_dir = data_dir
        self._file_path = os.path.join(data_dir, "allowed_users.json")
        self._users: dict[int, UserRecord] = {}
        self._pending_requests: set[int] = set()
        self._load()
        self._merge_seeds(seed_admin_ids, seed_user_ids)

    def _load(self) -> None:
        if not os.path.exists(self._file_path):
            log.info("user_store.no_file", path=self._file_path)
            return
        with open(self._file_path) as f:
            data = json.load(f)
        for record in data.get("users", []):
            uid = record["user_id"]
            self._users[uid] = UserRecord(
                user_id=uid,
                is_admin=record.get("is_admin", False),
                added_at=record.get("added_at", datetime.now(UTC).isoformat()),
            )
        log.info("user_store.loaded", count=len(self._users))

    def _save(self) -> None:
        os.makedirs(self._data_dir, exist_ok=True)
        data = {
            "users": [
                {
                    "user_id": r.user_id,
                    "is_admin": r.is_admin,
                    "added_at": r.added_at,
                }
                for r in self._users.values()
            ]
        }
        with open(self._file_path, "w") as f:
            json.dump(data, f, indent=2)
        log.info("user_store.saved", count=len(self._users))

    def _merge_seeds(
        self, admin_ids: list[int], user_ids: list[int]
    ) -> None:
        """Merge env seed IDs. Admins get is_admin=True, users get is_admin=False.
        Existing records are never downgraded."""
        changed = False
        for uid in admin_ids:
            if uid in self._users:
                if not self._users[uid].is_admin:
                    self._users[uid].is_admin = True
                    changed = True
            else:
                self._users[uid] = UserRecord(user_id=uid, is_admin=True)
                changed = True
        for uid in user_ids:
            if uid not in self._users:
                self._users[uid] = UserRecord(user_id=uid, is_admin=False)
                changed = True
        if changed:
            self._save()

    def is_allowed(self, user_id: int) -> bool:
        return user_id in self._users

    def is_admin(self, user_id: int) -> bool:
        record = self._users.get(user_id)
        return record is not None and record.is_admin

    def add_user(self, user_id: int, is_admin: bool = False) -> bool:
        """Add a user. Returns True if newly added, False if already present."""
        if user_id in self._users:
            return False
        self._users[user_id] = UserRecord(user_id=user_id, is_admin=is_admin)
        self._save()
        self._pending_requests.discard(user_id)
        return True

    def remove_user(self, user_id: int) -> bool:
        """Remove a user. Returns True if removed, False if not found."""
        if user_id not in self._users:
            return False
        del self._users[user_id]
        self._save()
        return True

    def get_admin_ids(self) -> list[int]:
        return [r.user_id for r in self._users.values() if r.is_admin]

    def has_pending_request(self, user_id: int) -> bool:
        return user_id in self._pending_requests

    def add_pending_request(self, user_id: int) -> None:
        self._pending_requests.add(user_id)

    def remove_pending_request(self, user_id: int) -> None:
        self._pending_requests.discard(user_id)

    @property
    def user_count(self) -> int:
        return len(self._users)

    @property
    def admin_count(self) -> int:
        return len(self.get_admin_ids())
