"""Password hashing (Argon2id) and the breach check (Have I Been Pwned)."""

import asyncio
import hashlib
import logging

import httpx
from pwdlib import PasswordHash

logger = logging.getLogger(__name__)

PWNED_RANGE_URL = "https://api.pwnedpasswords.com/range/"

# Argon2id with pwdlib's defaults (m=64 MiB, t=3, p=4), above OWASP's minimum
# (m=19 MiB, t=2, p=1).
_hasher = PasswordHash.recommended()
# Verified when the email is unknown, so a failed login takes the same time either way
# and its timing does not reveal which emails have accounts.
_DUMMY_HASH = _hasher.hash("timing-equalization-dummy-password")


async def is_breached(password: str, client: httpx.AsyncClient) -> bool:
    """Whether the password appears in Have I Been Pwned's breach corpus.

    Only the first 5 hex characters of its SHA-1 hash are sent (k-anonymity). If the
    service is unreachable the check is skipped rather than blocking signups.
    """
    digest = hashlib.sha1(password.encode()).hexdigest().upper()  # noqa: S324 (HIBP protocol)
    prefix, suffix = digest[:5], digest[5:]
    try:
        response = await client.get(
            PWNED_RANGE_URL + prefix, headers={"Add-Padding": "true"}, timeout=3
        )
        response.raise_for_status()
    except httpx.HTTPError:
        logger.warning("Pwned Passwords check unavailable; skipping it")
        return False
    for line in response.text.splitlines():
        candidate, _, count = line.partition(":")
        # Padding entries have a count of 0.
        if candidate == suffix and int(count or 0) > 0:
            return True
    return False


def hash_password(password: str) -> str:
    """Slow on purpose (tens of ms): call it in a thread from async code."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> tuple[bool, str | None]:
    """Returns (valid, new_hash). `new_hash` is set when the stored hash uses outdated
    parameters and should be replaced."""
    return _hasher.verify_and_update(password, password_hash)


def verify_dummy(password: str) -> None:
    _hasher.verify(password, _DUMMY_HASH)


class Argon2Hasher:
    """Runs the slow hashing in threads, so it does not block the event loop."""

    async def hash(self, password: str) -> str:
        return await asyncio.to_thread(hash_password, password)

    async def verify(self, password: str, password_hash: str) -> tuple[bool, str | None]:
        return await asyncio.to_thread(verify_password, password, password_hash)

    async def verify_dummy(self, password: str) -> None:
        await asyncio.to_thread(verify_dummy, password)


class HibpBreachChecker:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def contains(self, password: str) -> bool:
        return await is_breached(password, self._client)
