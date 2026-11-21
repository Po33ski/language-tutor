"""Account use cases: registering, verifying credentials, changing the password."""

from app.domain.accounts.models import User, WrongPasswordError
from app.domain.accounts.passwords import PasswordPolicyError, check_policy, normalize
from app.domain.ports import AccountStore, BreachChecker, PasswordHasher

BREACHED_MESSAGE = (
    "This password has appeared in a data breach, so attackers try it first. Choose another one."
)


class AccountService:
    def __init__(
        self,
        users: AccountStore,
        hasher: PasswordHasher,
        breach_checker: BreachChecker | None,
    ) -> None:
        self._users = users
        self._hasher = hasher
        # None when the check is turned off (`PASSWORD_BREACH_CHECK=false`).
        self._breach_checker = breach_checker

    async def _checked_hash(self, password: str, email: str) -> str:
        """Apply the password policy and return the hash; `PasswordPolicyError` if refused."""
        check_policy(password, email)
        if self._breach_checker is not None and await self._breach_checker.contains(password):
            raise PasswordPolicyError(BREACHED_MESSAGE)
        return await self._hasher.hash(password)

    async def register(self, email: str, password: str) -> User:
        """`email` is already normalized. Raises `PasswordPolicyError`, `EmailTakenError`."""
        password_hash = await self._checked_hash(normalize(password), email)
        return await self._users.create_user(email, password_hash)

    async def open_session(self, user: User) -> str:
        return await self._users.create_session(user.id)

    async def verify_credentials(self, email: str, password: str) -> User | None:
        """The user if the password is right. `email` is already normalized."""
        password = normalize(password)
        credentials = await self._users.get_credentials(email)
        if credentials is None:
            # Same work as a real check, so the response time does not reveal unknown emails.
            await self._hasher.verify_dummy(password)
            return None
        valid, new_hash = await self._hasher.verify(password, credentials.password_hash)
        if not valid:
            return None
        if new_hash:
            await self._users.update_password_hash(credentials.user.id, new_hash)
        return credentials.user

    async def change_password(
        self, user: User, current_password: str, new_password: str, keep_session_hash: str
    ) -> None:
        """Every other session is signed out. Raises `WrongPasswordError`,
        `PasswordPolicyError`."""
        credentials = await self._users.get_credentials(user.email)
        valid, _ = await self._hasher.verify(normalize(current_password), credentials.password_hash)
        if not valid:
            raise WrongPasswordError
        password_hash = await self._checked_hash(normalize(new_password), user.email)
        await self._users.change_password(
            user.id, password_hash, keep_session_hash=keep_session_hash
        )
