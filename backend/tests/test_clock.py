from datetime import UTC, datetime, timedelta

from langchain_core.messages import AIMessage, HumanMessage

from app.agent.clock import (
    CLOCK_NOTE_KEY,
    ClockPhase,
    LessonClock,
    with_clock_notes,
    wrap_up_seconds,
)


def test_wrap_up_is_a_fifth_of_the_lesson_between_one_and_three_minutes() -> None:
    assert wrap_up_seconds(5) == 60
    assert wrap_up_seconds(10) == 120
    assert wrap_up_seconds(15) == 180
    assert wrap_up_seconds(30) == 180


def test_phases_and_notes() -> None:
    start = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)

    on_track = LessonClock.at(start, 15, start + timedelta(minutes=4, seconds=30))
    assert on_track.phase is ClockPhase.ON_TRACK
    assert on_track.note() == "[Lesson clock: 4 of 15 minutes used, about 11 left.]"

    wrap_up = LessonClock.at(start, 15, start + timedelta(minutes=13))
    assert wrap_up.phase is ClockPhase.WRAP_UP
    assert "about 2 left. Start wrapping up" in wrap_up.note()

    time_up = LessonClock.at(start, 15, start + timedelta(minutes=16))
    assert time_up.phase is ClockPhase.TIME_UP
    assert time_up.remaining_seconds == 0
    assert time_up.note().startswith("[Lesson clock: time is up (15 of 15 minutes).")


def test_clock_notes_are_shown_to_the_model_only() -> None:
    noted = HumanMessage("I am work here.", additional_kwargs={CLOCK_NOTE_KEY: "[Clock]"})
    plain = HumanMessage("Hello")
    reply = AIMessage("Hi!")

    shown = with_clock_notes([plain, reply, noted])

    assert shown[0] is plain and shown[1] is reply
    assert shown[2].content == "[Clock]\n\nI am work here."
    assert CLOCK_NOTE_KEY not in shown[2].additional_kwargs
    # The stored message is unchanged, so the UI and the summary never see the note.
    assert noted.content == "I am work here."
    # Rendering is deterministic: earlier turns look the same on every model call.
    assert with_clock_notes([noted])[0].content == shown[2].content
