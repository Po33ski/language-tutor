"""Accounts: sign up, sign in, sign out, change the password.

Sessions are opaque bearer tokens (not cookies): the frontend and the API live on
different sites, where browsers (Safari above all) block third-party cookies.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, status
from langgraph.store.base import BaseStore
from pydantic import BaseModel, EmailStr, Field

from app.api.deps import HttpDep, SettingsDep, StoreDep, UsersDep
from app.api.security import CurrentSessionDep, CurrentUserDep, RateLimiter, client_ip
from app.auth.passwords import (
    PasswordPolicyError,
    check_policy,
    hash_password,
    is_breached,
    normalize,
    verify_dummy,
    verify_password,
)
from app.auth.store import EmailTakenError, User
from app.config import Settings
from app.storage import memory

router = APIRouter(prefix="/auth", tags=["auth"])

LOGIN_WINDOW_MINUTES = 15


@dataclass
class AuthLimiters:
    """In memory (the backend is one process). Signups count successes; logins count
    failures, per network and per account."""

    signups_per_ip: RateLimiter
    failed_logins_per_ip: RateLimiter
    failed_logins_per_email: RateLimiter

    @classmethod
    def from_settings(cls, settings: Settings) -> "AuthLimiters":
        window = LOGIN_WINDOW_MINUTES * 60
        return cls(
            signups_per_ip=RateLimiter(settings.signups_per_ip_per_hour, window_seconds=3600),
            failed_logins_per_ip=RateLimiter(30, window_seconds=window),
            failed_logins_per_email=RateLimiter(10, window_seconds=window),
        )


class Credentials(BaseModel):
    email: EmailStr
    # The password policy is checked separately, to return readable messages.
    password: str = Field(min_length=1, max_length=256)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class Account(BaseModel):
    id: str
    email: str
    created_at: datetime
    # False until the onboarding form has been filled in.
    has_profile: bool


class AuthResponse(BaseModel):
    # Send it as "Authorization: Bearer <token>". Shown once; the server keeps only a hash.
    token: str
    account: Account


def _limiters(request: Request) -> AuthLimiters:
    return request.app.state.auth_limiters


def _normalize_email(email: str) -> str:
    return email.strip().lower()


async def _account(user: User, store: BaseStore) -> Account:
    return Account(
        id=user.id,
        email=user.email,
        created_at=user.created_at,
        has_profile=await memory.get_profile(store, user.profile_id) is not None,
    )


async def _checked_password_hash(
    password: str, email: str, settings: Settings, http: HttpDep
) -> str:
    """Apply the password policy and return the Argon2id hash; 422 if not allowed."""
    try:
        check_policy(password, email)
    except PasswordPolicyError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    if settings.password_breach_check and await is_breached(password, http):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "This password has appeared in a data breach, so attackers try it first. "
            "Choose another one.",
        )
    return await asyncio.to_thread(hash_password, password)


@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def sign_up(
    data: Credentials,
    request: Request,
    users: UsersDep,
    store: StoreDep,
    settings: SettingsDep,
    http: HttpDep,
) -> AuthResponse:
    """Create an account and sign in. The learner profile is created next (onboarding)."""
    limiter = _limiters(request).signups_per_ip
    ip = client_ip(request)
    if limiter.is_limited(ip):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many new accounts from this network. Try again later.",
        )
    email = _normalize_email(data.email)
    password_hash = await _checked_password_hash(normalize(data.password), email, settings, http)
    try:
        user = await users.create_user(email, password_hash)
    except EmailTakenError as error:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "An account with this email already exists. Sign in instead."
        ) from error
    limiter.record(ip)
    token = await users.create_session(user.id)
    return AuthResponse(token=token, account=await _account(user, store))


@router.post("/login")
async def sign_in(
    data: Credentials, request: Request, users: UsersDep, store: StoreDep
) -> AuthResponse:
    limiters = _limiters(request)
    ip = client_ip(request)
    email = _normalize_email(data.email)
    if limiters.failed_logins_per_ip.is_limited(ip) or limiters.failed_logins_per_email.is_limited(
        email
    ):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many sign-in attempts. Wait {LOGIN_WINDOW_MINUTES} minutes and try again.",
        )
    password = normalize(data.password)
    credentials = await users.get_credentials(email)
    new_hash = None
    if credentials is None:
        # Same work as a real check, so the response time does not reveal unknown emails.
        await asyncio.to_thread(verify_dummy, password)
        valid = False
    else:
        valid, new_hash = await asyncio.to_thread(
            verify_password, password, credentials.password_hash
        )
    if not valid:
        limiters.failed_logins_per_ip.record(ip)
        limiters.failed_logins_per_email.record(email)
        # One message for both cases: do not reveal whether the email has an account.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")
    if new_hash:
        await users.update_password_hash(credentials.user.id, new_hash)
    token = await users.create_session(credentials.user.id)
    return AuthResponse(token=token, account=await _account(credentials.user, store))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def sign_out(session: CurrentSessionDep, users: UsersDep) -> None:
    """End this session (the token stops working immediately)."""
    await users.delete_session(session.token_hash)


@router.get("/me")
async def me(user: CurrentUserDep, store: StoreDep) -> Account:
    return await _account(user, store)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    data: PasswordChange,
    request: Request,
    session: CurrentSessionDep,
    users: UsersDep,
    settings: SettingsDep,
    http: HttpDep,
) -> None:
    """Change the password; every other session of this account is signed out."""
    user = session.user
    failed = _limiters(request).failed_logins_per_email
    if failed.is_limited(user.email):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many attempts. Wait {LOGIN_WINDOW_MINUTES} minutes and try again.",
        )
    credentials = await users.get_credentials(user.email)
    valid, _ = await asyncio.to_thread(
        verify_password, normalize(data.current_password), credentials.password_hash
    )
    if not valid:
        failed.record(user.email)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your current password is incorrect.")
    password_hash = await _checked_password_hash(
        normalize(data.new_password), user.email, settings, http
    )
    await users.change_password(user.id, password_hash, keep_session_hash=session.token_hash)
