"""Access control for a publicly reachable backend: a shared access key and a rate limit."""

import secrets
import time
from collections import deque
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.deps import SettingsDep

_bearer = HTTPBearer(auto_error=False, description="The backend's ACCESS_KEY")


async def require_access_key(
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> None:
    """Reject requests without `Authorization: Bearer <ACCESS_KEY>`.

    With no `ACCESS_KEY` configured (local development) every request is allowed.
    """
    expected = settings.access_key
    if not expected:
        return
    if credentials is None or not secrets.compare_digest(
        credentials.credentials.encode(), expected.encode()
    ):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid or missing access key",
            headers={"WWW-Authenticate": "Bearer"},
        )


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
        now = self._clock()
        if len(self._hits) > 1000:
            self._forget_idle_clients(now)
        hits = self._hits.setdefault(client, deque())
        while hits and hits[0] <= now - self._window:
            hits.popleft()
        if len(hits) >= self._max_requests:
            return False
        hits.append(now)
        return True

    def _forget_idle_clients(self, now: float) -> None:
        idle = [client for client, hits in self._hits.items() if hits[-1] <= now - self._window]
        for client in idle:
            del self._hits[client]


def rate_limit(request: Request) -> None:
    """Limit endpoints that cost money (LLM calls) or a lot of CPU (speech models)."""
    limiter: RateLimiter | None = request.app.state.rate_limiter
    if limiter is None:
        return
    # Behind the reverse proxy, uvicorn's --proxy-headers puts the real client IP here.
    client = request.client.host if request.client else "unknown"
    if not limiter.allow(client):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many requests. Wait a minute and try again.",
            headers={"Retry-After": "60"},
        )
