"""Admin commands for accounts.

On the server (in `~/language-tutor/deploy`):

    docker compose exec backend python -m app.cli list-users
    docker compose exec backend python -m app.cli reset-password EMAIL
    docker compose exec backend python -m app.cli claim-profile EMAIL [--profile-id ID]

Locally: `uv run python -m app.cli ...` from `backend/`. Safe to run while the
backend is running (SQLite handles the concurrent access).
"""

import argparse
import asyncio
import secrets
import sys
from datetime import datetime

from langgraph.store.sqlite.aio import AsyncSqliteStore

from app.config import Settings
from app.domain.accounts.models import ProfileTakenError, User, normalize_email
from app.domain.learners.models import Profile
from app.domain.ports import LearnerMemory
from app.infra.persistence.learner_memory import LearnerMemoryStore
from app.infra.persistence.users import UserStore
from app.infra.security.passwords import hash_password


def _fail(message: str) -> None:
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(1)


async def _require_user(users: UserStore, email: str) -> User:
    credentials = await users.get_credentials(normalize_email(email))
    if credentials is None:
        _fail(f"no account with the email {email}")
    return credentials.user


async def list_users(users: UserStore, memory: LearnerMemory) -> None:
    accounts = await users.list_users()
    if not accounts:
        print("No accounts yet.")
    for user in accounts:
        profile = await memory.get_profile(user.profile_id)
        name = profile.name if profile else "(no profile yet)"
        print(f"{user.email:40} {name:20} since {user.created_at:%Y-%m-%d}")


async def reset_password(users: UserStore, email: str) -> None:
    """Set a random temporary password and sign out all sessions of the account."""
    user = await _require_user(users, email)
    temporary = secrets.token_urlsafe(18)  # 24 characters, above the 15-character minimum
    await users.change_password(user.id, await asyncio.to_thread(hash_password, temporary))
    print(f"Temporary password for {user.email}: {temporary}")
    print("All sessions were signed out. Change it in the app (Account) after signing in.")


async def _last_activity(memory: LearnerMemory, profile: Profile) -> datetime:
    lessons = await memory.list_lessons(profile.id)
    return max((lesson.created_at for lesson in lessons), default=profile.created_at)


async def claim_profile(
    users: UserStore, memory: LearnerMemory, email: str, profile_id: str | None, force: bool
) -> None:
    """Link a profile created before accounts existed (with its lessons and progress) to
    an account. Without --profile-id, the most recently used unclaimed profile is taken."""
    user = await _require_user(users, email)
    linked = await users.linked_profile_ids()
    unclaimed = [p for p in await memory.list_profiles() if p.id not in linked]
    if not unclaimed:
        print("There are no unclaimed profiles.")
        return
    print("Unclaimed profiles:")
    for profile in unclaimed:
        lessons = await memory.list_lessons(profile.id)
        print(f"  {profile.id}  {profile.name:20} {len(lessons)} lesson(s)")

    if profile_id:
        chosen = next((p for p in unclaimed if p.id == profile_id), None)
        if chosen is None:
            _fail(f"{profile_id} is not an unclaimed profile")
    else:
        activity = {p.id: await _last_activity(memory, p) for p in unclaimed}
        chosen = max(unclaimed, key=lambda p: activity[p.id])

    if await memory.get_profile(user.profile_id) is not None and not force:
        _fail(
            "this account already has its own profile. Use --force to replace it "
            "(its lessons stay in the database but are no longer shown)."
        )
    try:
        await users.set_profile_id(user.id, chosen.id)
    except ProfileTakenError:
        _fail(f"profile {chosen.id} was just claimed by another account")
    print(f"Linked '{chosen.name}' ({chosen.id}) to {user.email}.")


async def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list-users", help="list accounts")
    reset = commands.add_parser("reset-password", help="set a temporary password")
    reset.add_argument("email")
    claim = commands.add_parser("claim-profile", help="link a pre-accounts profile")
    claim.add_argument("email")
    claim.add_argument("--profile-id", help="the profile to link (default: most recently used)")
    claim.add_argument("--force", action="store_true", help="replace the account's own profile")
    args = parser.parse_args(argv)

    settings = Settings()
    async with (
        UserStore.open(settings.users_db_path) as users,
        AsyncSqliteStore.from_conn_string(str(settings.memory_db_path)) as store,
    ):
        await store.setup()
        memory = LearnerMemoryStore(store)
        if args.command == "list-users":
            await list_users(users, memory)
        elif args.command == "reset-password":
            await reset_password(users, args.email)
        else:
            await claim_profile(users, memory, args.email, args.profile_id, args.force)


if __name__ == "__main__":
    asyncio.run(main())
