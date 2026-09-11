import hashlib
import json
import os
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
import structlog

log = structlog.get_logger()

_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS bot_users (
    telegram_user_id   bigint PRIMARY KEY,
    telegram_username  text,
    display_name       text,
    authentik_sub      text UNIQUE,
    authentik_username text,
    role               text NOT NULL DEFAULT 'user'
                       CHECK (role IN ('user', 'operator', 'admin')),
    status             text NOT NULL DEFAULT 'pending'
                       CHECK (status IN ('pending', 'active', 'denied', 'disabled')),
    requested_at       timestamptz,
    added_at           timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS access_link_tokens (
    token_hash       text PRIMARY KEY,
    telegram_user_id bigint NOT NULL REFERENCES bot_users(telegram_user_id) ON DELETE CASCADE,
    expires_at       timestamptz NOT NULL,
    used_at          timestamptz
);

CREATE TABLE IF NOT EXISTS runtime_settings (
    key        text PRIMARY KEY,
    value      text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    updated_by text
);

CREATE TABLE IF NOT EXISTS access_audit_log (
    id               bigserial PRIMARY KEY,
    ts               timestamptz NOT NULL DEFAULT now(),
    actor             text NOT NULL,
    action            text NOT NULL,
    telegram_user_id bigint,
    details           jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_bot_users_status ON bot_users(status);
CREATE INDEX IF NOT EXISTS idx_access_link_expiry ON access_link_tokens(expires_at);
"""

_INTEGER_SETTING_RANGES = {
    "max_duration": (1, 3600),
    "max_file_size": (1, 2000),
}
_GROUP_ACCESS_MODES = {"open", "allowed_users", "disabled"}


class AccountAlreadyLinkedError(Exception):
    pass


@dataclass
class UserRecord:
    user_id: int
    is_admin: bool = False
    role: str = "user"
    status: str = "active"
    telegram_username: str | None = None
    display_name: str | None = None
    authentik_sub: str | None = None
    authentik_username: str | None = None
    added_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class UserStore:
    """PostgreSQL-backed access store with a synchronous authorization cache."""

    def __init__(
        self,
        data_dir: str,
        seed_admin_ids: list[int],
        seed_user_ids: list[int],
        *,
        dsn: str | None = None,
        runtime_defaults: dict[str, str] | None = None,
    ) -> None:
        self._data_dir = data_dir
        self._file_path = os.path.join(data_dir, "allowed_users.json")
        self._dsn = dsn
        self._pool: Any = None
        self._users: dict[int, UserRecord] = {}
        self._pending_requests: set[int] = set()
        self._runtime_settings = dict(runtime_defaults or {})
        self._load_legacy_file()
        self._merge_seeds(seed_admin_ids, seed_user_ids)

    @property
    def database_enabled(self) -> bool:
        return self._dsn is not None

    async def initialize(self) -> None:
        if not self.database_enabled:
            return
        self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=3)
        async with self._pool.acquire() as conn:
            await conn.execute(_SCHEMA_DDL)
            for record in self._users.values():
                await conn.execute(
                    """
                    INSERT INTO bot_users (telegram_user_id, role, status, added_at)
                    VALUES ($1, $2, 'active', $3)
                    ON CONFLICT (telegram_user_id) DO UPDATE SET
                        role = CASE
                            WHEN bot_users.role = 'admin' OR EXCLUDED.role = 'admin'
                            THEN 'admin' ELSE bot_users.role
                        END,
                        status = CASE
                            WHEN EXCLUDED.role = 'admin' THEN 'active' ELSE bot_users.status
                        END,
                        updated_at = now()
                    """,
                    record.user_id,
                    "admin" if record.is_admin else record.role,
                    datetime.fromisoformat(record.added_at),
                )
            for key, value in self._runtime_settings.items():
                await conn.execute(
                    """
                    INSERT INTO runtime_settings (key, value, updated_by)
                    VALUES ($1, $2, 'environment-default')
                    ON CONFLICT (key) DO NOTHING
                    """,
                    key,
                    value,
                )
        await self.refresh()
        log.info("user_store.database_ready", users=len(self._users))

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()

    async def refresh(self) -> None:
        if self._pool is None:
            return
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT telegram_user_id, telegram_username, display_name,
                       authentik_sub, authentik_username, role, status, added_at
                FROM bot_users
                """
            )
            settings = await conn.fetch("SELECT key, value FROM runtime_settings")
        users: dict[int, UserRecord] = {}
        pending: set[int] = set()
        for row in rows:
            user_id = row["telegram_user_id"]
            status = row["status"]
            record = UserRecord(
                user_id=user_id,
                is_admin=row["role"] == "admin" and status == "active",
                role=row["role"],
                status=status,
                telegram_username=row["telegram_username"],
                display_name=row["display_name"],
                authentik_sub=row["authentik_sub"],
                authentik_username=row["authentik_username"],
                added_at=row["added_at"].isoformat(),
            )
            users[user_id] = record
            if status == "pending":
                pending.add(user_id)
        self._users = users
        self._pending_requests = pending
        self._runtime_settings = {row["key"]: row["value"] for row in settings}

    def _load_legacy_file(self) -> None:
        if not os.path.exists(self._file_path):
            log.info("user_store.no_file", path=self._file_path)
            return
        with open(self._file_path) as file:
            data = json.load(file)
        for raw in data.get("users", []):
            user_id = int(raw["user_id"])
            is_admin = bool(raw.get("is_admin", False))
            self._users[user_id] = UserRecord(
                user_id=user_id,
                is_admin=is_admin,
                role="admin" if is_admin else "user",
                added_at=raw.get("added_at", datetime.now(UTC).isoformat()),
            )
        log.info("user_store.legacy_loaded", count=len(self._users))

    def _save_legacy_file(self) -> None:
        os.makedirs(self._data_dir, exist_ok=True)
        data = {
            "users": [
                {
                    "user_id": record.user_id,
                    "is_admin": record.is_admin,
                    "added_at": record.added_at,
                }
                for record in self._users.values()
                if record.status == "active"
            ]
        }
        with open(self._file_path, "w") as file:
            json.dump(data, file, indent=2)

    def _merge_seeds(self, admin_ids: list[int], user_ids: list[int]) -> None:
        changed = False
        for user_id in admin_ids:
            record = self._users.get(user_id)
            if record:
                if not record.is_admin:
                    record.is_admin = True
                    record.role = "admin"
                    changed = True
            else:
                self._users[user_id] = UserRecord(user_id=user_id, is_admin=True, role="admin")
                changed = True
        for user_id in user_ids:
            if user_id not in self._users:
                self._users[user_id] = UserRecord(user_id=user_id)
                changed = True
        if changed and not self.database_enabled:
            self._save_legacy_file()

    def is_allowed(self, user_id: int) -> bool:
        record = self._users.get(user_id)
        return record is not None and record.status == "active"

    def is_admin(self, user_id: int) -> bool:
        record = self._users.get(user_id)
        return record is not None and record.status == "active" and record.role == "admin"

    def has_pending_request(self, user_id: int) -> bool:
        return user_id in self._pending_requests

    async def add_pending_request(
        self,
        user_id: int,
        *,
        username: str | None = None,
        display_name: str | None = None,
    ) -> bool:
        if self.is_allowed(user_id) or self.has_pending_request(user_id):
            return False
        if self._pool is None:
            self._pending_requests.add(user_id)
            self._users[user_id] = UserRecord(
                user_id=user_id,
                status="pending",
                telegram_username=username,
                display_name=display_name,
            )
            return True
        await self._pool.execute(
            """
            INSERT INTO bot_users (
                telegram_user_id, telegram_username, display_name, status, requested_at
            ) VALUES ($1, $2, $3, 'pending', now())
            ON CONFLICT (telegram_user_id) DO UPDATE SET
                telegram_username = EXCLUDED.telegram_username,
                display_name = EXCLUDED.display_name,
                status = CASE WHEN bot_users.status = 'active' THEN 'active' ELSE 'pending' END,
                requested_at = CASE
                    WHEN bot_users.status = 'active' THEN bot_users.requested_at ELSE now()
                END,
                updated_at = now()
            """,
            user_id,
            username,
            display_name,
        )
        await self.refresh()
        return self.has_pending_request(user_id)

    async def add_user(
        self,
        user_id: int,
        is_admin: bool = False,
        *,
        actor: str = "telegram-admin",
        username: str | None = None,
        display_name: str | None = None,
    ) -> bool:
        was_allowed = self.is_allowed(user_id)
        role = "admin" if is_admin else "user"
        if self._pool is None:
            self._users[user_id] = UserRecord(
                user_id=user_id,
                is_admin=is_admin,
                role=role,
                telegram_username=username,
                display_name=display_name,
            )
            self._pending_requests.discard(user_id)
            self._save_legacy_file()
            return not was_allowed
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                """
                INSERT INTO bot_users (
                    telegram_user_id, telegram_username, display_name, role, status
                ) VALUES ($1, $2, $3, $4, 'active')
                ON CONFLICT (telegram_user_id) DO UPDATE SET
                    telegram_username = coalesce(
                        EXCLUDED.telegram_username, bot_users.telegram_username
                    ),
                    display_name = coalesce(EXCLUDED.display_name, bot_users.display_name),
                    role = CASE
                        WHEN EXCLUDED.role = 'admin' THEN 'admin' ELSE bot_users.role
                    END,
                    status = 'active',
                    updated_at = now()
                """,
                user_id,
                username,
                display_name,
                role,
            )
            await self._audit(conn, actor, "approve", user_id)
        await self.refresh()
        return not was_allowed

    async def deny_user(self, user_id: int, *, actor: str) -> None:
        await self._set_status(user_id, "denied", actor=actor)

    async def disable_user(self, user_id: int, *, actor: str) -> None:
        await self._set_status(user_id, "disabled", actor=actor)

    async def _set_status(self, user_id: int, status: str, *, actor: str) -> None:
        if self._pool is None:
            record = self._users.get(user_id)
            if record:
                record.status = status
                self._save_legacy_file()
            self._pending_requests.discard(user_id)
            return
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "UPDATE bot_users SET status = $2, updated_at = now() WHERE telegram_user_id = $1",
                user_id,
                status,
            )
            await self._audit(conn, actor, status, user_id)
        await self.refresh()

    async def set_role(self, user_id: int, role: str, *, actor: str) -> None:
        if role not in {"user", "operator", "admin"}:
            raise ValueError("Invalid role")
        if self._pool is None:
            record = self._users[user_id]
            record.role = role
            record.is_admin = role == "admin"
            self._save_legacy_file()
            return
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "UPDATE bot_users SET role = $2, updated_at = now() WHERE telegram_user_id = $1",
                user_id,
                role,
            )
            await self._audit(conn, actor, "set_role", user_id, {"role": role})
        await self.refresh()

    async def list_users(self) -> list[UserRecord]:
        if self._pool is not None:
            await self.refresh()
        return sorted(self._users.values(), key=lambda user: (user.status, user.user_id))

    async def create_link_token(
        self,
        user_id: int,
        *,
        username: str | None,
        display_name: str | None,
    ) -> str:
        if self._pool is None:
            raise RuntimeError("Account linking requires PostgreSQL")
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        expires_at = datetime.now(UTC) + timedelta(minutes=10)
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                """
                INSERT INTO bot_users (telegram_user_id, telegram_username, display_name)
                VALUES ($1, $2, $3)
                ON CONFLICT (telegram_user_id) DO UPDATE SET
                    telegram_username = EXCLUDED.telegram_username,
                    display_name = EXCLUDED.display_name,
                    updated_at = now()
                """,
                user_id,
                username,
                display_name,
            )
            await conn.execute(
                "DELETE FROM access_link_tokens WHERE telegram_user_id = $1 OR expires_at < now()",
                user_id,
            )
            await conn.execute(
                """
                INSERT INTO access_link_tokens (token_hash, telegram_user_id, expires_at)
                VALUES ($1, $2, $3)
                """,
                token_hash,
                user_id,
                expires_at,
            )
        return token

    async def consume_link_token(
        self,
        token: str,
        *,
        authentik_sub: str,
        authentik_username: str,
    ) -> int | None:
        if self._pool is None:
            return None
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        async with self._pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT telegram_user_id
                FROM access_link_tokens
                WHERE token_hash = $1 AND used_at IS NULL AND expires_at > now()
                FOR UPDATE
                """,
                token_hash,
            )
            if row is None:
                return None
            user_id = int(row["telegram_user_id"])
            existing_user_id = await conn.fetchval(
                "SELECT telegram_user_id FROM bot_users WHERE authentik_sub = $1",
                authentik_sub,
            )
            if existing_user_id is not None and int(existing_user_id) != user_id:
                raise AccountAlreadyLinkedError
            await conn.execute(
                """
                UPDATE bot_users
                SET authentik_sub = $2, authentik_username = $3, updated_at = now()
                WHERE telegram_user_id = $1
                """,
                user_id,
                authentik_sub,
                authentik_username,
            )
            await conn.execute(
                "UPDATE access_link_tokens SET used_at = now() WHERE token_hash = $1",
                token_hash,
            )
            await self._audit(conn, f"authentik:{authentik_sub}", "link", user_id)
        await self.refresh()
        return user_id

    def get_runtime(self, key: str, fallback: str) -> str:
        return self._runtime_settings.get(key, fallback)

    def get_runtime_int(self, key: str, fallback: int) -> int:
        try:
            return int(self.get_runtime(key, str(fallback)))
        except ValueError:
            return fallback

    async def set_runtime_setting(self, key: str, value: str, *, actor: str) -> None:
        await self.set_runtime_settings({key: value}, actor=actor)

    async def set_runtime_settings(self, values: dict[str, str], *, actor: str) -> None:
        normalized = {
            key: self._validate_setting(key, value) for key, value in values.items()
        }
        if self._pool is None:
            raise RuntimeError("Runtime settings require PostgreSQL")
        async with self._pool.acquire() as conn, conn.transaction():
            for key, value in normalized.items():
                await conn.execute(
                    """
                    INSERT INTO runtime_settings (key, value, updated_by)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (key) DO UPDATE SET
                        value = EXCLUDED.value,
                        updated_at = now(),
                        updated_by = EXCLUDED.updated_by
                    """,
                    key,
                    value,
                    actor,
                )
            await self._audit(
                conn,
                actor,
                "settings_changed",
                None,
                {"keys": sorted(normalized)},
            )
        await self.refresh()

    @staticmethod
    def _validate_setting(key: str, value: str) -> str:
        value = value.strip().lower()
        if key == "group_access_mode":
            if value not in _GROUP_ACCESS_MODES:
                raise ValueError("Invalid setting value")
            return value
        limits = _INTEGER_SETTING_RANGES.get(key)
        if limits is None:
            raise ValueError("Unknown runtime setting")
        number = int(value)
        minimum, maximum = limits
        if not minimum <= number <= maximum:
            raise ValueError(f"Value must be between {minimum} and {maximum}")
        return str(number)

    @staticmethod
    async def _audit(
        conn: Any,
        actor: str,
        action: str,
        user_id: int | None,
        details: dict[str, Any] | None = None,
    ) -> None:
        await conn.execute(
            """
            INSERT INTO access_audit_log (actor, action, telegram_user_id, details)
            VALUES ($1, $2, $3, $4::jsonb)
            """,
            actor,
            action,
            user_id,
            json.dumps(details or {}),
        )

    @property
    def user_count(self) -> int:
        return sum(user.status == "active" for user in self._users.values())

    @property
    def admin_count(self) -> int:
        return sum(
            user.status == "active" and user.role == "admin" for user in self._users.values()
        )

    def get_admin_ids(self) -> list[int]:
        return [
            user.user_id
            for user in self._users.values()
            if user.status == "active" and user.role == "admin"
        ]
