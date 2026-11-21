"""The users database (SQLite, `data/users.db`): accounts, sessions and usage counters.

Kept apart from the learning data (LangGraph store and checkpointer). An account owns
exactly one learner profile, linked by `profile_id`.

Session tokens are random 256-bit strings. Only their SHA-256 hash is stored, so a copy
of this database does not contain working tokens.
"""

import hashlib
import secrets
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import aiosqlite

from app.domain.accounts.models import (
    EmailTakenError,
    ProfileTakenError,
    User,
    UserCredentials,
)

SCHEMA_VERSION = 1

_SCHEMA_V1 = """
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    profile_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    password_changed_at TEXT NOT NULL
);
CREATE TABLE sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    last_used_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX sessions_by_user ON sessions(user_id);
CREATE TABLE daily_usage (
    day TEXT NOT NULL,
    scope TEXT NOT NULL,
    kind TEXT NOT NULL,
    count INTEGER NOT NULL,
    PRIMARY KEY (day, scope, kind)
);
"""

# How often a session's last use is written back (and its expiry slid forward).
_TOUCH_INTERVAL = timedelta(hours=1)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


def _user(row: aiosqlite.Row) -> User:
    return User(
        id=row["id"],
        email=row["email"],
        profile_id=row["profile_id"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


class UserStore:
    def __init__(
        self, db: aiosqlite.Connection, session_idle: timedelta, session_max: timedelta
    ) -> None:
        self._db = db
        self._session_idle = session_idle
        self._session_max = session_max

    @classmethod
    @asynccontextmanager
    async def open(
        cls,
        path: Path,
        session_idle: timedelta = timedelta(days=30),
        session_max: timedelta = timedelta(days=90),
    ) -> AsyncIterator["UserStore"]:
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA foreign_keys = ON")
            await db.execute("PRAGMA journal_mode = WAL")
            await db.execute("PRAGMA busy_timeout = 5000")
            store = cls(db, session_idle, session_max)
            await store._migrate()
            yield store

    async def _migrate(self) -> None:
        async with self._db.execute("PRAGMA user_version") as cursor:
            (version,) = await cursor.fetchone()
        if version < 1:
            await self._db.executescript(_SCHEMA_V1)
        await self._db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        await self._db.commit()

    # --- Users -------------------------------------------------------------------

    async def create_user(self, email: str, password_hash: str) -> User:
        now = _now().isoformat()
        user = User(id=uuid4().hex, email=email, profile_id=uuid4().hex, created_at=_now())
        try:
            await self._db.execute(
                "INSERT INTO users (id, email, password_hash, profile_id, created_at,"
                " password_changed_at) VALUES (?, ?, ?, ?, ?, ?)",
                (user.id, email, password_hash, user.profile_id, now, now),
            )
            await self._db.commit()
        except sqlite3.IntegrityError as error:
            await self._db.rollback()
            raise EmailTakenError(email) from error
        return user

    async def get_credentials(self, email: str) -> UserCredentials | None:
        async with self._db.execute("SELECT * FROM users WHERE email = ?", (email,)) as cursor:
            row = await cursor.fetchone()
        return UserCredentials(_user(row), row["password_hash"]) if row else None

    async def get_user(self, user_id: str) -> User | None:
        async with self._db.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
        return _user(row) if row else None

    async def list_users(self) -> list[User]:
        async with self._db.execute("SELECT * FROM users ORDER BY created_at") as cursor:
            return [_user(row) for row in await cursor.fetchall()]

    async def update_password_hash(self, user_id: str, password_hash: str) -> None:
        """Store a rehash of the same password (stronger parameters); sessions stay."""
        await self._db.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id)
        )
        await self._db.commit()

    async def change_password(
        self, user_id: str, password_hash: str, keep_session_hash: str | None = None
    ) -> None:
        """Set a new password and sign out every other session."""
        await self._db.execute(
            "UPDATE users SET password_hash = ?, password_changed_at = ? WHERE id = ?",
            (password_hash, _now().isoformat(), user_id),
        )
        await self._db.execute(
            "DELETE FROM sessions WHERE user_id = ? AND token_hash IS NOT ?",
            (user_id, keep_session_hash),
        )
        await self._db.commit()

    async def set_profile_id(self, user_id: str, profile_id: str) -> None:
        try:
            await self._db.execute(
                "UPDATE users SET profile_id = ? WHERE id = ?", (profile_id, user_id)
            )
            await self._db.commit()
        except sqlite3.IntegrityError as error:
            await self._db.rollback()
            raise ProfileTakenError(profile_id) from error

    async def linked_profile_ids(self) -> set[str]:
        async with self._db.execute("SELECT profile_id FROM users") as cursor:
            return {row["profile_id"] for row in await cursor.fetchall()}

    # --- Sessions ----------------------------------------------------------------

    async def create_session(self, user_id: str) -> str:
        """Start a session and return its token (shown to the client once, never stored)."""
        token = secrets.token_urlsafe(32)
        now = _now()
        await self._db.execute(
            "INSERT INTO sessions (token_hash, user_id, created_at, last_used_at, expires_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                hash_token(token),
                user_id,
                now.isoformat(),
                now.isoformat(),
                (now + self._session_idle).isoformat(),
            ),
        )
        await self._db.commit()
        return token

    async def authenticate(self, token: str) -> tuple[User, str] | None:
        """The user behind a session token and the token's hash, or None if the token is
        unknown or expired. Using a session slides its expiry forward."""
        token_hash = hash_token(token)
        async with self._db.execute(
            "SELECT users.*, sessions.created_at AS session_created_at,"
            " sessions.last_used_at, sessions.expires_at"
            " FROM sessions JOIN users ON users.id = sessions.user_id"
            " WHERE sessions.token_hash = ?",
            (token_hash,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        now = _now()
        created = datetime.fromisoformat(row["session_created_at"])
        hard_limit = created + self._session_max
        if now >= datetime.fromisoformat(row["expires_at"]) or now >= hard_limit:
            await self.delete_session(token_hash)
            return None
        if now - datetime.fromisoformat(row["last_used_at"]) >= _TOUCH_INTERVAL:
            await self._db.execute(
                "UPDATE sessions SET last_used_at = ?, expires_at = ? WHERE token_hash = ?",
                (
                    now.isoformat(),
                    min(now + self._session_idle, hard_limit).isoformat(),
                    token_hash,
                ),
            )
            await self._db.commit()
        return _user(row), token_hash

    async def delete_session(self, token_hash: str) -> None:
        await self._db.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
        await self._db.commit()

    async def delete_user_sessions(self, user_id: str) -> int:
        cursor = await self._db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        await self._db.commit()
        return cursor.rowcount

    # --- Usage limits ------------------------------------------------------------

    async def consume(self, day: date, scope: str, kind: str, limit: int) -> bool:
        """Count one use of `kind` for `scope` (a user id, or "*" for the whole app) and
        return False, without counting, once today's `limit` is reached."""
        cursor = await self._db.execute(
            "INSERT INTO daily_usage (day, scope, kind, count) VALUES (?, ?, ?, 1)"
            " ON CONFLICT (day, scope, kind) DO UPDATE SET count = count + 1"
            " WHERE count < ?",
            (day.isoformat(), scope, kind, limit),
        )
        await self._db.commit()
        return cursor.rowcount == 1

    # --- Housekeeping ------------------------------------------------------------

    async def purge(self) -> None:
        """Drop expired sessions and usage counters older than a week."""
        now = _now()
        await self._db.execute("DELETE FROM sessions WHERE expires_at <= ?", (now.isoformat(),))
        await self._db.execute(
            "DELETE FROM daily_usage WHERE day < ?", ((now - timedelta(days=7)).date().isoformat(),)
        )
        await self._db.commit()
