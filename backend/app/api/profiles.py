from fastapi import APIRouter, HTTPException, status

from app.api.deps import StoreDep
from app.storage import memory
from app.storage.memory import Profile, ProfileCreate, Progress

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("")
async def list_profiles(store: StoreDep) -> list[Profile]:
    return await memory.list_profiles(store)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_profile(data: ProfileCreate, store: StoreDep) -> Profile:
    return await memory.create_profile(store, data)


@router.get("/{user_id}")
async def get_profile(user_id: str, store: StoreDep) -> Profile:
    profile = await memory.get_profile(store, user_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile not found")
    return profile


@router.get("/{user_id}/progress")
async def get_progress(user_id: str, store: StoreDep) -> Progress | None:
    """The learner's progress profile; null until the first lesson is summarized."""
    return await memory.get_progress(store, user_id)
