"""The learner: the profile from the onboarding form and the progress description."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class EnglishLevel(StrEnum):
    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"


MIN_LESSON_MINUTES = 5
MAX_LESSON_MINUTES = 30
DEFAULT_LESSON_MINUTES = 15


class ProfileCreate(BaseModel):
    """The learner's main preferences: set in the onboarding form, editable later."""

    name: str = Field(min_length=1, max_length=50)
    level: EnglishLevel
    main_topic: str = Field(min_length=1, max_length=200)
    goal: str = Field(default="", max_length=500)
    # Free-form preferences: "notes" from the form, others saved by the tutor.
    preferences: dict[str, str] = Field(default_factory=dict)
    # Planned length of each lesson. Profiles from before this field get the default.
    lesson_minutes: int = Field(
        default=DEFAULT_LESSON_MINUTES, ge=MIN_LESSON_MINUTES, le=MAX_LESSON_MINUTES
    )


class Profile(ProfileCreate):
    id: str
    created_at: datetime


class Progress(BaseModel):
    """Cumulative description of the learner, updated after every summarized lesson."""

    text: str
    updated_at: datetime
