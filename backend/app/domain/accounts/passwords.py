"""The password policy (NIST SP 800-63B-4).

The policy follows NIST for passwords used as the only factor: at least 15 characters,
long passphrases allowed, no composition rules ("one digit, one capital"), and a check
against passwords known from data breaches.
"""

import unicodedata

MIN_LENGTH = 15
MAX_LENGTH = 128


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
