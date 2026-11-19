"""Password hashing (Argon2id) and the password policy (NIST SP 800-63B-4).

The policy follows NIST for passwords used as the only factor: at least 15 characters,
long passphrases allowed, no composition rules ("one digit, one capital"), and a check
against passwords known from data breaches.
"""

import hashlib
import logging
import unicodedata

import httpx
from pwdlib import PasswordHash

logger = logging.getLogger(__name__)

MIN_LENGTH = 15
MAX_LENGTH = 128
PWNED_RANGE_URL = "https://api.pwnedpasswords.com/range/"

# Argon2id with pwdlib's defaults (m=64 MiB, t=3, p=4), above OWASP's minimum
# (m=19 MiB, t=2, p=1).
_hasher = PasswordHash.recommended()
# Verified when the email is unknown, so a failed login takes the same time either way
# and its timing does not reveal which emails have accounts.
_DUMMY_HASH = _hasher.hash("timing-equalization-dummy-password")


class PasswordPolicyError(ValueError):
    """The password is not allowed; the message can be shown to the user."""


def normalize(password: str) -> str:
    """NFKC, as NIST asks, so the same password typed on another keyboard still matches."""
    return unicodedata.normalize("NFKC", password)


def check_policy(password: str, email: str) -> None:
    length = len(password)
    if length < MIN_LENGTH:
        raise PasswordPolicyError(
            f"Use at least {MIN_LENGTH} characters. A few random words make a strong "
            "password that is easy to remember."
        )
    if length > MAX_LENGTH:
        raise PasswordPolicyError(f"Use at most {MAX_LENGTH} characters.")
    if len(set(password)) < 5:
        raise PasswordPolicyError("This password is too repetitive. Choose another one.")
    lowered = password.lower()
    local_part = email.split("@", 1)[0].lower()
    if (len(local_part) >= 4 and local_part in lowered) or "languagetutor" in lowered.replace(
        " ", ""
    ):
        raise PasswordPolicyError("Do not use your email or the app's name in the password.")


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
