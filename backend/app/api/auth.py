"""Accounts: sign up, sign in, sign out, change the password.

Sessions are opaque bearer tokens (not cookies): the frontend and the API live on
different sites, where browsers (Safari above all) block third-party cookies.
"""

from dataclasses import dataclass
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field

from app.api.deps import AccountsDep, MemoryDep, UsersDep
from app.api.security import CurrentSessionDep, CurrentUserDep, RateLimiter, client_ip
from app.config import Settings
from app.domain.accounts.models import EmailTakenError, User, WrongPasswordError, normalize_email
from app.domain.accounts.passwords import PasswordPolicyError
from app.domain.ports import LearnerMemory

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


async def _account(user: User, memory: LearnerMemory) -> Account:
    return Account(
        id=user.id,
        email=user.email,
        created_at=user.created_at,
        has_profile=await memory.get_profile(user.profile_id) is not None,
    )


@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def sign_up(
    data: Credentials,
    request: Request,
    accounts: AccountsDep,
    memory: MemoryDep,
) -> AuthResponse:
    """Create an account and sign in. The learner profile is created next (onboarding)."""
    limiter = _limiters(request).signups_per_ip
    ip = client_ip(request)
    if limiter.is_limited(ip):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many new accounts from this network. Try again later.",
        )
    try:
        user = await accounts.register(normalize_email(data.email), data.password)
    except PasswordPolicyError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    except EmailTakenError as error:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "An account with this email already exists. Sign in instead."
        ) from error
    limiter.record(ip)
    token = await accounts.open_session(user)
    return AuthResponse(token=token, account=await _account(user, memory))


@router.post("/login")
async def sign_in(
    data: Credentials, request: Request, accounts: AccountsDep, memory: MemoryDep
) -> AuthResponse:
    limiters = _limiters(request)
    ip = client_ip(request)
    email = normalize_email(data.email)
    if limiters.failed_logins_per_ip.is_limited(ip) or limiters.failed_logins_per_email.is_limited(
        email
    ):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many sign-in attempts. Wait {LOGIN_WINDOW_MINUTES} minutes and try again.",
        )
    user = await accounts.verify_credentials(email, data.password)
    if user is None:
        limiters.failed_logins_per_ip.record(ip)
        limiters.failed_logins_per_email.record(email)
        # One message for both cases: do not reveal whether the email has an account.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")
    token = await accounts.open_session(user)
    return AuthResponse(token=token, account=await _account(user, memory))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def sign_out(session: CurrentSessionDep, users: UsersDep) -> None:
    """End this session (the token stops working immediately)."""
    await users.delete_session(session.token_hash)


@router.get("/me")
async def me(user: CurrentUserDep, memory: MemoryDep) -> Account:
    return await _account(user, memory)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    data: PasswordChange,
    request: Request,
    session: CurrentSessionDep,
    accounts: AccountsDep,
) -> None:
    """Change the password; every other session of this account is signed out."""
    user = session.user
    failed = _limiters(request).failed_logins_per_email
    if failed.is_limited(user.email):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many attempts. Wait {LOGIN_WINDOW_MINUTES} minutes and try again.",
        )
    try:
        await accounts.change_password(
            user, data.current_password, data.new_password, session.token_hash
        )
    except WrongPasswordError as error:
        failed.record(user.email)
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Your current password is incorrect."
        ) from error
    except PasswordPolicyError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
