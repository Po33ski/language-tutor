"""What the domain needs from the outside world. `app/infra` implements these."""

from collections.abc import AsyncIterator
from datetime import date
from typing import Protocol

from app.domain.accounts.models import User, UserCredentials
from app.domain.learners.models import Profile, ProfileCreate, Progress
from app.domain.lessons.models import (
    Lesson,
    LessonContext,
    LessonConversation,
    LessonSummary,
    Mistake,
    TutorEvent,
    VocabularyItem,
)
from app.domain.moderation.policy import ModerationVerdict


class LearnerMemory(Protocol):
    """Long-term memory: profiles, lessons and progress."""

    async def create_profile(
        self, data: ProfileCreate, profile_id: str | None = None
    ) -> Profile: ...

    async def get_profile(self, user_id: str) -> Profile | None: ...

    async def list_profiles(self) -> list[Profile]: ...

    async def update_profile(self, user_id: str, data: ProfileCreate) -> Profile | None: ...

    async def save_preference(self, user_id: str, key: str, value: str) -> None: ...

    async def create_lesson(
        self, user_id: str, topic: str, duration_minutes: int | None = None
    ) -> Lesson: ...

    async def save_lesson(self, lesson: Lesson) -> None: ...

    async def get_lesson(self, lesson_id: str) -> Lesson | None: ...

    async def list_lessons(self, user_id: str) -> list[Lesson]: ...

    async def list_active_lessons(self) -> list[Lesson]: ...

    async def recent_summaries(self, user_id: str, count: int) -> list[dict]: ...

    async def get_progress(self, user_id: str) -> Progress | None: ...

    async def set_progress(self, user_id: str, text: str) -> Progress: ...


class Tutor(Protocol):
    """The conversational agent. One lesson is one conversation."""

    async def conversation(self, lesson_id: str) -> LessonConversation: ...

    def start(self, lesson_id: str, context: LessonContext) -> AsyncIterator[TutorEvent]:
        """The tutor opens the lesson."""
        ...

    def reply(self, lesson_id: str, text: str, clock_note: str | None) -> AsyncIterator[TutorEvent]:
        """The tutor answers a learner message."""
        ...


class Summarizer(Protocol):
    async def summarize(
        self,
        *,
        profile: Profile,
        topic: str,
        transcript: str,
        mistakes: list[Mistake],
        vocabulary: list[VocabularyItem],
    ) -> LessonSummary: ...

    async def update_progress(
        self, *, profile: Profile, previous: str, date: str, topic: str, summary: LessonSummary
    ) -> str: ...


class Moderator(Protocol):
    async def check(self, text: str) -> ModerationVerdict: ...

    async def warm_up(self) -> None: ...


class SpeechService(Protocol):
    async def transcribe(self, audio: bytes) -> str: ...

    @property
    def hosted_tts_enabled(self) -> bool:
        """Whether a paid hosted engine is configured."""
        ...

    async def synthesize(self, text: str, *, allow_hosted: bool = False) -> bytes:
        """Speech as WAV. Only `allow_hosted=True` may use (and pay for) the hosted engine."""
        ...

    async def warm_up(self) -> None: ...

    async def close(self) -> None: ...


class AccountStore(Protocol):
    """Accounts, sessions and daily usage counters."""

    async def create_user(self, email: str, password_hash: str) -> User: ...

    async def get_credentials(self, email: str) -> UserCredentials | None: ...

    async def update_password_hash(self, user_id: str, password_hash: str) -> None: ...

    async def change_password(
        self, user_id: str, password_hash: str, keep_session_hash: str | None = None
    ) -> None: ...

    async def create_session(self, user_id: str) -> str: ...

    async def authenticate(self, token: str) -> tuple[User, str] | None: ...

    async def delete_session(self, token_hash: str) -> None: ...

    async def consume(
        self, day: date, scope: str, kind: str, limit: int, amount: int = 1
    ) -> bool: ...


class PasswordHasher(Protocol):
    async def hash(self, password: str) -> str: ...

    async def verify(self, password: str, password_hash: str) -> tuple[bool, str | None]:
        """Returns (valid, new_hash); `new_hash` is set when the stored hash is outdated."""
        ...

    async def verify_dummy(self, password: str) -> None:
        """Takes as long as a real check, for emails that have no account."""
        ...


class BreachChecker(Protocol):
    async def contains(self, password: str) -> bool:
        """Whether the password is known from data breaches."""
        ...
