"""Accounts: one account owns exactly one learner profile, linked by `profile_id`."""

from dataclasses import dataclass
from datetime import datetime


class EmailTakenError(Exception):
    pass


class ProfileTakenError(Exception):
    pass


class WrongPasswordError(Exception):
    """The current password given to confirm a change is incorrect."""


@dataclass(frozen=True)
class User:
    id: str
    email: str
    profile_id: str
    created_at: datetime


@dataclass(frozen=True)
class UserCredentials:
    user: User
    password_hash: str


def normalize_email(email: str) -> str:
    return email.strip().lower()
