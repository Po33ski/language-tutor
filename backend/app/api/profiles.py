"""The signed-in account's learner profile (one per account)."""

from fastapi import APIRouter, HTTPException, status

from app.api.deps import MemoryDep
from app.api.security import CurrentUserDep
from app.domain.learners.models import Profile, ProfileCreate, Progress

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("")
async def get_profile(user: CurrentUserDep, memory: MemoryDep) -> Profile:
    """404 until the onboarding form has been filled in."""
    profile = await memory.get_profile(user.profile_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No profile yet")
    return profile


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_profile(data: ProfileCreate, user: CurrentUserDep, memory: MemoryDep) -> Profile:
    """Create the profile from the onboarding form; 409 if the account already has one."""
    if await memory.get_profile(user.profile_id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "You already have a profile")
    return await memory.create_profile(data, user.profile_id)


@router.put("")
async def update_profile(data: ProfileCreate, user: CurrentUserDep, memory: MemoryDep) -> Profile:
    """Replace the learner's main preferences (the edit-profile form sends every field).

    Lessons already in progress keep the settings they started with.
    """
    profile = await memory.update_profile(user.profile_id, data)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No profile yet")
    return profile


@router.get("/progress")
async def get_progress(user: CurrentUserDep, memory: MemoryDep) -> Progress | None:
    """The learner's progress profile; null until the first lesson is summarized."""
    return await memory.get_progress(user.profile_id)
