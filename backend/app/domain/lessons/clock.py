"""The lesson clock: how much of a lesson's time is used, and what the tutor should do.

The system prompt must stay the same for a whole lesson (thinking blocks are bound to
it), so the ticking time cannot live there. Instead, every learner message carries a
short clock note (see `app/infra/agent/clock_notes.py`). The note is stored with the
message, so earlier turns look exactly the same to the model on every call.
"""

import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ClockPhase(StrEnum):
    ON_TRACK = "on_track"
    # The final stretch: no new topics, finish the conversation.
    WRAP_UP = "wrap_up"
    # The tutor's next reply is its closing message; then the lesson ends.
    TIME_UP = "time_up"


def wrap_up_seconds(duration_minutes: int) -> int:
    """Length of the final stretch: 20% of the lesson, between 1 and 3 minutes."""
    return 60 * min(3, max(1, round(duration_minutes * 0.2)))


@dataclass(frozen=True)
class LessonClock:
    duration_minutes: int
    elapsed_seconds: float

    @classmethod
    def at(cls, started_at: datetime, duration_minutes: int, now: datetime) -> "LessonClock":
        elapsed = max(0.0, (now - started_at).total_seconds())
        return cls(duration_minutes=duration_minutes, elapsed_seconds=elapsed)

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.duration_minutes * 60 - self.elapsed_seconds)

    @property
    def phase(self) -> ClockPhase:
        if self.remaining_seconds <= 0:
            return ClockPhase.TIME_UP
        if self.remaining_seconds <= wrap_up_seconds(self.duration_minutes):
            return ClockPhase.WRAP_UP
        return ClockPhase.ON_TRACK

    def note(self) -> str:
        """The note shown to the tutor with a learner message (the prompt explains it)."""
        total = self.duration_minutes
        if self.phase is ClockPhase.TIME_UP:
            return (
                f"[Lesson clock: time is up ({total} of {total} minutes). "
                "Give your closing message now.]"
            )
        used = min(total, math.floor(self.elapsed_seconds / 60))
        left = math.ceil(self.remaining_seconds / 60)
        note = f"[Lesson clock: {used} of {total} minutes used, about {left} left."
        if self.phase is ClockPhase.WRAP_UP:
            note += " Start wrapping up: no new topics."
        return note + "]"
