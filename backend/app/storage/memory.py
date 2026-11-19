"""Long-term memory: profiles, lessons and progress, kept in the LangGraph store."""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from langgraph.store.base import BaseStore
from pydantic import BaseModel, Field

PROFILES_NS = ("profiles",)
LESSONS_NS = ("lessons",)
# Max items fetched by a single store search; far above what one local user creates.
SEARCH_LIMIT = 1000


def _now() -> datetime:
    return datetime.now(UTC)


def _progress_ns(user_id: str) -> tuple[str, ...]:
    return ("users", user_id)


class EnglishLevel(StrEnum):
    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"


class ProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    level: EnglishLevel
    main_topic: str = Field(min_length=1, max_length=200)
    goal: str = Field(default="", max_length=500)
    preferences: dict[str, str] = Field(default_factory=dict)


class Profile(ProfileCreate):
    id: str
    created_at: datetime


class LessonStatus(StrEnum):
    ACTIVE = "active"
    SUMMARIZED = "summarized"
    # Ended before the learner said anything, so there was nothing to summarize.
    DISCARDED = "discarded"


class LessonSummary(BaseModel):
    """Structured summary of one finished lesson."""

    summary: str = Field(description="2-3 sentences describing the lesson.")
    practiced: list[str] = Field(description="Skills and situations practiced.")
    recurring_mistakes: list[str] = Field(description="Mistakes the learner made repeatedly.")
    vocabulary: list[str] = Field(description="New words and phrases introduced.")
    next_steps: list[str] = Field(description="Recommendations for the next lesson.")


class Lesson(BaseModel):
    id: str
    user_id: str
    topic: str
    status: LessonStatus = LessonStatus.ACTIVE
    created_at: datetime
    ended_at: datetime | None = None
    summary: LessonSummary | None = None


class Progress(BaseModel):
    """Cumulative description of the learner, updated after every summarized lesson."""

    text: str
    updated_at: datetime


# --- Profiles -----------------------------------------------------------------


async def create_profile(
    store: BaseStore, data: ProfileCreate, profile_id: str | None = None
) -> Profile:
    """`profile_id` comes from the account that owns the profile (`users.profile_id`)."""
    profile = Profile(id=profile_id or uuid4().hex, created_at=_now(), **data.model_dump())
    await store.aput(PROFILES_NS, profile.id, profile.model_dump(mode="json"))
    return profile


async def get_profile(store: BaseStore, user_id: str) -> Profile | None:
    item = await store.aget(PROFILES_NS, user_id)
    return Profile.model_validate(item.value) if item else None


async def list_profiles(store: BaseStore) -> list[Profile]:
    items = await store.asearch(PROFILES_NS, limit=SEARCH_LIMIT)
    profiles = [Profile.model_validate(item.value) for item in items]
    return sorted(profiles, key=lambda p: p.created_at)


async def save_preference(store: BaseStore, user_id: str, key: str, value: str) -> None:
    profile = await get_profile(store, user_id)
    if profile is None:
        return
    profile.preferences[key] = value
    await store.aput(PROFILES_NS, user_id, profile.model_dump(mode="json"))


# --- Lessons ------------------------------------------------------------------


async def create_lesson(store: BaseStore, user_id: str, topic: str) -> Lesson:
    lesson = Lesson(id=uuid4().hex, user_id=user_id, topic=topic, created_at=_now())
    await store.aput(LESSONS_NS, lesson.id, lesson.model_dump(mode="json"))
    return lesson


async def save_lesson(store: BaseStore, lesson: Lesson) -> None:
    await store.aput(LESSONS_NS, lesson.id, lesson.model_dump(mode="json"))


async def get_lesson(store: BaseStore, lesson_id: str) -> Lesson | None:
    item = await store.aget(LESSONS_NS, lesson_id)
    return Lesson.model_validate(item.value) if item else None


async def list_lessons(store: BaseStore, user_id: str) -> list[Lesson]:
    """Lessons of one user, newest first."""
    items = await store.asearch(LESSONS_NS, filter={"user_id": user_id}, limit=SEARCH_LIMIT)
    lessons = [Lesson.model_validate(item.value) for item in items]
    return sorted(lessons, key=lambda lesson: lesson.created_at, reverse=True)


async def list_active_lessons(store: BaseStore) -> list[Lesson]:
    """Active lessons of all users."""
    items = await store.asearch(
        LESSONS_NS, filter={"status": LessonStatus.ACTIVE.value}, limit=SEARCH_LIMIT
    )
    return [Lesson.model_validate(item.value) for item in items]


async def recent_summaries(store: BaseStore, user_id: str, count: int) -> list[dict]:
    """The `count` most recent lesson summaries, oldest first (prompt-ready dicts)."""
    lessons = [lesson for lesson in await list_lessons(store, user_id) if lesson.summary]
    return [
        {"topic": lesson.topic, "date": lesson.created_at.date().isoformat()}
        | lesson.summary.model_dump()
        for lesson in reversed(lessons[:count])
    ]


# --- Progress profile -----------------------------------------------------------


async def get_progress(store: BaseStore, user_id: str) -> Progress | None:
    item = await store.aget(_progress_ns(user_id), "progress")
    return Progress.model_validate(item.value) if item else None


async def set_progress(store: BaseStore, user_id: str, text: str) -> Progress:
    progress = Progress(text=text, updated_at=_now())
    await store.aput(_progress_ns(user_id), "progress", progress.model_dump(mode="json"))
    return progress
