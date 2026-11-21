"""Lessons: what is stored about them and what happens during a tutor turn."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal, TypedDict

from pydantic import BaseModel, Field

from app.domain.learners.models import Profile
from app.domain.moderation.policy import ModerationVerdict


class Mistake(TypedDict):
    original: str
    corrected: str
    explanation: str


class VocabularyItem(TypedDict):
    word: str
    meaning: str
    example: str


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


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
    # The lesson clock starts here (the tutor's opening turn follows at once).
    created_at: datetime
    # Copied from the profile when the lesson is created; None for older lessons.
    duration_minutes: int | None = None
    ended_at: datetime | None = None
    summary: LessonSummary | None = None


@dataclass(frozen=True)
class LessonContext:
    """Learner context copied from long-term memory into a lesson when it starts."""

    user_id: str
    profile: Profile | None
    topic: str
    progress: str
    previous_summaries: list[dict]
    lesson_minutes: int | None


@dataclass(frozen=True)
class LessonConversation:
    """A lesson's conversation so far, as the tutor runtime has stored it."""

    started: bool
    messages: list[ChatMessage]
    mistakes: list[Mistake]
    vocabulary: list[VocabularyItem]
    # When the lesson's state last changed; None before the first turn.
    last_activity: datetime | None
    # Long lessons: the summary of the oldest turns, and the turns after it.
    earlier_summary: str
    recent_messages: list[ChatMessage]


@dataclass(frozen=True)
class LessonView:
    lesson: Lesson
    conversation: LessonConversation
    # Measured by the server; None for ended lessons and lessons without a planned length.
    time_left_seconds: int | None


@dataclass(frozen=True)
class TurnRequest:
    """An accepted request for a turn; `blocked` is set when moderation stopped the text."""

    lesson: Lesson
    blocked: ModerationVerdict | None = None


# --- What happens during a turn --------------------------------------------------


@dataclass(frozen=True)
class TutorToken:
    text: str


@dataclass(frozen=True)
class MistakeRecorded:
    mistake: Mistake


@dataclass(frozen=True)
class VocabularyAdded:
    item: VocabularyItem


@dataclass(frozen=True)
class TurnFailed:
    message: str


@dataclass(frozen=True)
class LessonTimeUp:
    """This reply was the tutor's closing message: the lesson's time is over."""


@dataclass(frozen=True)
class TurnDone:
    pass


TutorEvent = TutorToken | MistakeRecorded | VocabularyAdded
TurnEvent = TutorEvent | TurnFailed | LessonTimeUp | TurnDone


# --- Errors ----------------------------------------------------------------------


class LessonNotFoundError(Exception):
    """No such lesson, or it belongs to someone else (the two are not told apart)."""


class ProfileRequiredError(Exception):
    pass


class LessonEndedError(Exception):
    pass


class LessonBusyError(Exception):
    """The tutor is still answering in this lesson."""


class EmptyMessageError(Exception):
    pass


class LessonSummaryError(Exception):
    """The lesson could not be summarized; it stays active, so ending can be retried."""
