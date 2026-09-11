from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from bot.services.user_store import AccountAlreadyLinkedError, UserStore


class _AsyncContext:
    def __init__(self, value: object) -> None:
        self.value = value

    async def __aenter__(self) -> object:
        return self.value

    async def __aexit__(self, *args: object) -> bool:
        return False


class _FakeConnection:
    def __init__(self) -> None:
        self.execute = AsyncMock()
        self.fetch = AsyncMock(return_value=[])
        self.fetchrow = AsyncMock()
        self.fetchval = AsyncMock()

    def transaction(self) -> _AsyncContext:
        return _AsyncContext(None)


class _FakePool:
    def __init__(self, connection: _FakeConnection) -> None:
        self.connection = connection
        self.execute = AsyncMock()

    def acquire(self) -> _AsyncContext:
        return _AsyncContext(self.connection)

    async def close(self) -> None:
        return None


def _store(tmp_path: Path) -> UserStore:
    return UserStore(
        str(tmp_path),
        seed_admin_ids=[1],
        seed_user_ids=[2],
        runtime_defaults={"max_duration": "300"},
    )


def test_seeded_users_keep_legacy_mode_working(tmp_path: Path) -> None:
    store = _store(tmp_path)

    assert store.is_admin(1)
    assert store.is_allowed(2)
    assert store.user_count == 2
    assert (tmp_path / "allowed_users.json").exists()


@pytest.mark.asyncio
async def test_pending_request_can_be_approved(tmp_path: Path) -> None:
    store = _store(tmp_path)

    assert await store.add_pending_request(3, username="new_user", display_name="New User")
    assert store.has_pending_request(3)
    assert not store.is_allowed(3)

    assert await store.add_user(3, actor="test")
    assert store.is_allowed(3)
    assert not store.has_pending_request(3)


@pytest.mark.asyncio
async def test_denial_clears_legacy_pending_request(tmp_path: Path) -> None:
    store = _store(tmp_path)
    await store.add_pending_request(3)

    await store.deny_user(3, actor="test")

    assert not store.has_pending_request(3)
    assert not store.is_allowed(3)


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("max_duration", "600", "600"),
        ("max_file_size", "50", "50"),
        ("group_access_mode", "ALLOWED_USERS", "allowed_users"),
    ],
)
def test_runtime_setting_validation(key: str, value: str, expected: str) -> None:
    assert UserStore._validate_setting(key, value) == expected


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("max_duration", "0"),
        ("max_file_size", "2001"),
        ("group_access_mode", "members"),
        ("unknown", "1"),
    ],
)
def test_invalid_runtime_settings_are_rejected(key: str, value: str) -> None:
    with pytest.raises(ValueError):
        UserStore._validate_setting(key, value)


@pytest.mark.asyncio
async def test_linking_requires_postgres(tmp_path: Path) -> None:
    store = _store(tmp_path)

    with pytest.raises(RuntimeError, match="PostgreSQL"):
        await store.create_link_token(2, username=None, display_name=None)


@pytest.mark.asyncio
async def test_postgres_initialization_creates_schema_and_migrates_seeds(
    tmp_path: Path,
) -> None:
    store = UserStore(
        str(tmp_path),
        seed_admin_ids=[1],
        seed_user_ids=[2],
        dsn="postgresql://unused",
        runtime_defaults={"max_duration": "300"},
    )
    connection = _FakeConnection()
    pool = _FakePool(connection)

    with (
        patch("bot.services.user_store.asyncpg.create_pool", AsyncMock(return_value=pool)),
        patch.object(store, "refresh", AsyncMock()) as refresh,
    ):
        await store.initialize()

    assert connection.execute.await_args_list[0].args[0] == "SELECT pg_advisory_xact_lock($1)"
    assert "CREATE TABLE IF NOT EXISTS bot_users" in connection.execute.await_args_list[1].args[0]
    assert connection.execute.await_count == 5
    refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_one_authentik_identity_cannot_link_to_two_telegram_users(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    connection = _FakeConnection()
    connection.fetchrow.return_value = {"telegram_user_id": 2}
    connection.fetchval.return_value = 99
    store._pool = _FakePool(connection)

    with pytest.raises(AccountAlreadyLinkedError):
        await store.consume_link_token(
            "token",
            authentik_sub="authentik-sub",
            authentik_username="askar",
        )


@pytest.mark.asyncio
async def test_observed_identity_is_persisted_without_creating_or_linking_user(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    pool = _FakePool(_FakeConnection())
    store._pool = pool

    store.observe_identity(2, username="telegram_name", display_name="Telegram Name")
    await store.close()

    sql = pool.execute.await_args.args[0]
    assert sql.lstrip().startswith("UPDATE bot_users")
    assert "authentik" not in sql
    assert pool.execute.await_args.args[1:] == (2, "telegram_name", "Telegram Name")


@pytest.mark.asyncio
async def test_observed_identity_ignores_users_without_access_records(tmp_path: Path) -> None:
    store = _store(tmp_path)
    pool = _FakePool(_FakeConnection())
    store._pool = pool

    store.observe_identity(99, username="outsider", display_name="Outsider")
    await store.close()

    pool.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_observed_identity_database_failure_does_not_escape(tmp_path: Path) -> None:
    store = _store(tmp_path)
    pool = _FakePool(_FakeConnection())
    pool.execute.side_effect = RuntimeError("database unavailable")
    store._pool = pool

    store.observe_identity(2, username=None, display_name="Updated Name")
    await store.close()


@pytest.mark.asyncio
async def test_runtime_settings_are_all_validated_before_database_write(tmp_path: Path) -> None:
    store = _store(tmp_path)
    pool = _FakePool(_FakeConnection())
    store._pool = pool

    with pytest.raises(ValueError):
        await store.set_runtime_settings(
            {"max_duration": "600", "group_access_mode": "invalid"},
            actor="test",
        )

    pool.connection.execute.assert_not_awaited()
