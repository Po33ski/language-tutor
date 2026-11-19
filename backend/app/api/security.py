"""Access control for a publicly reachable backend: sessions, rate limits, daily quotas."""

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.deps import SettingsDep, UsersDep
from app.auth.store import User

_bearer = HTTPBearer(
    auto_error=False, description="Session token from /api/auth/signup or /api/auth/login"
)


@dataclass(frozen=True)
class CurrentSession:
    user: User
    token_hash: str


async def get_current_session(
    users: UsersDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CurrentSession:
    """The signed-in user, from `Authorization: Bearer <session token>`; 401 otherwise."""
    found = await users.authenticate(credentials.credentials) if credentials else None
    if found is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Please sign in",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user, token_hash = found
    return CurrentSession(user, token_hash)


CurrentSessionDep = Annotated[CurrentSession, Depends(get_current_session)]


async def get_current_user(session: CurrentSessionDep) -> User:
    return session.user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


# Daily limits per kind of costly action: (per-user setting, whole-app setting).
_QUOTAS = {
    "tutor_turn": ("user_daily_tutor_turns", "daily_tutor_turns_total"),
    "transcription": ("user_daily_transcriptions", None),
}


def daily_quota(kind: str) -> Callable:
    """A dependency counting one `kind` action against today's limits (UTC days).

    Signup is open to anyone, so these cap what one account, and the whole app, can
    spend per day on the LLM and on speech to text.
    """
    user_setting, total_setting = _QUOTAS[kind]

    async def dependency(user: CurrentUserDep, users: UsersDep, settings: SettingsDep) -> None:
        today = datetime.now(UTC).date()
        user_limit = getattr(settings, user_setting)
        if user_limit and not await users.consume(today, user.id, kind, user_limit):
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "You have reached today's limit. Come back tomorrow!",
            )
        total_limit = getattr(settings, total_setting) if total_setting else 0
        if total_limit and not await users.consume(today, "*", kind, total_limit):
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "The tutor is very busy today. Please come back tomorrow.",
            )

    return dependency


class RateLimiter:
    """Sliding-window request limit per client, kept in memory.

    In-memory state is enough because the backend runs as a single process (the speech
    models and per-lesson locks already require that).
    """

    def __init__(
        self,
        max_requests: int,
        window_seconds: float = 60,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_requests = max_requests
        self._window = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}

    def allow(self, client: str) -> bool:
        """Count one request; False (and not counted) once the client is over the limit."""
        if self.is_limited(client):
            return False
        self.record(client)
        return True

    def is_limited(self, client: str) -> bool:
        return len(self._recent(client)) >= self._max_requests

    def record(self, client: str) -> None:
        """Count one event without checking, e.g. a failed login."""
        self._recent(client).append(self._clock())

    def _recent(self, client: str) -> deque[float]:
        now = self._clock()
        if len(self._hits) > 1000:
            self._forget_idle_clients(now)
        hits = self._hits.setdefault(client, deque())
        while hits and hits[0] <= now - self._window:
            hits.popleft()
        return hits

    def _forget_idle_clients(self, now: float) -> None:
        idle = [
            client
            for client, hits in self._hits.items()
            if not hits or hits[-1] <= now - self._window
        ]
        for client in idle:
            del self._hits[client]


def client_ip(request: Request) -> str:
    # Behind the reverse proxy, uvicorn's --proxy-headers puts the real client IP here.
    return request.client.host if request.client else "unknown"


def rate_limited(group: str) -> Callable[[Request], None]:
    """A dependency limiting one group of endpoints that cost money (LLM calls) or a lot
    of CPU (speech models). Each group has its own budget per client, so reading a reply
    aloud sentence by sentence does not use up the budget for tutor turns."""

    def dependency(request: Request) -> None:
        limiter: RateLimiter | None = request.app.state.rate_limiter
        if limiter is None:
            return
        if not limiter.allow(f"{group}:{client_ip(request)}"):
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Too many requests. Wait a minute and try again.",
                headers={"Retry-After": "60"},
            )

    return dependency
