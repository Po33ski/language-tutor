"""Long-term memory: profiles, lessons and progress, kept in the LangGraph store."""

from datetime import UTC, datetime
from uuid import uuid4

from langgraph.store.base import BaseStore

from app.domain.learners.models import Profile, ProfileCreate, Progress
from app.domain.lessons.models import Lesson, LessonStatus

PROFILES_NS = ("profiles",)
LESSONS_NS = ("lessons",)
# Max items fetched by a single store search; far above what one local user creates.
SEARCH_LIMIT = 1000


def _now() -> datetime:
    return datetime.now(UTC)


def _progress_ns(user_id: str) -> tuple[str, ...]:
    return ("users", user_id)


class LearnerMemoryStore:
    def __init__(self, store: BaseStore) -> None:
        self._store = store

    # --- Profiles -----------------------------------------------------------------

    async def create_profile(self, data: ProfileCreate, profile_id: str | None = None) -> Profile:
        """`profile_id` comes from the account that owns the profile (`users.profile_id`)."""
        profile = Profile(id=profile_id or uuid4().hex, created_at=_now(), **data.model_dump())
        await self._store.aput(PROFILES_NS, profile.id, profile.model_dump(mode="json"))
        return profile

    async def get_profile(self, user_id: str) -> Profile | None:
        item = await self._store.aget(PROFILES_NS, user_id)
        return Profile.model_validate(item.value) if item else None

    async def list_profiles(self) -> list[Profile]:
        items = await self._store.asearch(PROFILES_NS, limit=SEARCH_LIMIT)
        profiles = [Profile.model_validate(item.value) for item in items]
        return sorted(profiles, key=lambda p: p.created_at)

    async def update_profile(self, user_id: str, data: ProfileCreate) -> Profile | None:
        """Replace the editable fields; the id and creation date stay. None if no profile."""
        profile = await self.get_profile(user_id)
        if profile is None:
            return None
        updated = profile.model_copy(update=data.model_dump())
        await self._store.aput(PROFILES_NS, user_id, updated.model_dump(mode="json"))
        return updated

    async def save_preference(self, user_id: str, key: str, value: str) -> None:
        profile = await self.get_profile(user_id)
        if profile is None:
            return
        profile.preferences[key] = value
        await self._store.aput(PROFILES_NS, user_id, profile.model_dump(mode="json"))

    # --- Lessons ------------------------------------------------------------------

    async def create_lesson(
        self, user_id: str, topic: str, duration_minutes: int | None = None
    ) -> Lesson:
        lesson = Lesson(
            id=uuid4().hex,
            user_id=user_id,
            topic=topic,
            created_at=_now(),
            duration_minutes=duration_minutes,
        )
        await self._store.aput(LESSONS_NS, lesson.id, lesson.model_dump(mode="json"))
        return lesson

    async def save_lesson(self, lesson: Lesson) -> None:
        await self._store.aput(LESSONS_NS, lesson.id, lesson.model_dump(mode="json"))

    async def get_lesson(self, lesson_id: str) -> Lesson | None:
        item = await self._store.aget(LESSONS_NS, lesson_id)
        return Lesson.model_validate(item.value) if item else None

    async def list_lessons(self, user_id: str) -> list[Lesson]:
        """Lessons of one user, newest first."""
        items = await self._store.asearch(
            LESSONS_NS, filter={"user_id": user_id}, limit=SEARCH_LIMIT
        )
        lessons = [Lesson.model_validate(item.value) for item in items]
        return sorted(lessons, key=lambda lesson: lesson.created_at, reverse=True)

    async def list_active_lessons(self) -> list[Lesson]:
        """Active lessons of all users."""
        items = await self._store.asearch(
            LESSONS_NS, filter={"status": LessonStatus.ACTIVE.value}, limit=SEARCH_LIMIT
        )
        return [Lesson.model_validate(item.value) for item in items]

    async def recent_summaries(self, user_id: str, count: int) -> list[dict]:
        """The `count` most recent lesson summaries, oldest first (prompt-ready dicts)."""
        lessons = [lesson for lesson in await self.list_lessons(user_id) if lesson.summary]
        return [
            {"topic": lesson.topic, "date": lesson.created_at.date().isoformat()}
            | lesson.summary.model_dump()
            for lesson in reversed(lessons[:count])
        ]

    # --- Progress profile -----------------------------------------------------------

    async def get_progress(self, user_id: str) -> Progress | None:
        item = await self._store.aget(_progress_ns(user_id), "progress")
        return Progress.model_validate(item.value) if item else None

    async def set_progress(self, user_id: str, text: str) -> Progress:
        progress = Progress(text=text, updated_at=_now())
        await self._store.aput(_progress_ns(user_id), "progress", progress.model_dump(mode="json"))
        return progress
