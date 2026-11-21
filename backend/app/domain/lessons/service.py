"""Lesson use cases: starting, running one turn at a time, ending."""

import asyncio
import logging
from collections import defaultdict
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime, timedelta

from app.domain.lessons.clock import ClockPhase, LessonClock
from app.domain.lessons.models import (
    ChatMessage,
    EmptyMessageError,
    Lesson,
    LessonBusyError,
    LessonContext,
    LessonConversation,
    LessonEndedError,
    LessonNotFoundError,
    LessonStatus,
    LessonSummaryError,
    LessonTimeUp,
    LessonView,
    ProfileRequiredError,
    TurnDone,
    TurnEvent,
    TurnFailed,
    TurnRequest,
)
from app.domain.ports import LearnerMemory, Moderator, Summarizer, Tutor

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


def _clock(lesson: Lesson) -> LessonClock | None:
    if lesson.duration_minutes is None:
        return None
    return LessonClock.at(lesson.created_at, lesson.duration_minutes, _now())


def format_transcript(messages: Sequence[ChatMessage]) -> str:
    speakers = {"user": "Learner", "assistant": "Tutor"}
    return "\n\n".join(f"{speakers[m.role]}: {m.content}" for m in messages)


def _lesson_transcript(conversation: LessonConversation) -> str:
    """For the end-of-lesson summary. In a long lesson the oldest turns come as their
    summary, so this call stays affordable too."""
    recent = format_transcript(conversation.recent_messages)
    if not conversation.earlier_summary:
        return recent
    return (
        f"Summary of the earlier part of the lesson:\n{conversation.earlier_summary}\n\n"
        f"Transcript of the rest:\n{recent}"
    )


class LessonService:
    def __init__(
        self,
        memory: LearnerMemory,
        tutor: Tutor,
        summarizer: Summarizer,
        moderator: Moderator | None,
        recent_summaries_count: int,
    ) -> None:
        self._memory = memory
        self._tutor = tutor
        self._summarizer = summarizer
        self._moderator = moderator  # None when moderation is off
        self._recent_summaries_count = recent_summaries_count
        # One lock per lesson, so a lesson never runs two agent turns at once.
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def create(self, profile_id: str, topic: str | None) -> Lesson:
        """A new lesson; its topic defaults to the profile's main topic."""
        profile = await self._memory.get_profile(profile_id)
        if profile is None:
            raise ProfileRequiredError
        topic = (topic or "").strip() or profile.main_topic
        return await self._memory.create_lesson(profile.id, topic, profile.lesson_minutes)

    async def list_for_learner(self, profile_id: str) -> list[Lesson]:
        return await self._memory.list_lessons(profile_id)

    async def _owned(self, lesson_id: str, profile_id: str) -> Lesson:
        """Someone else's lesson is reported as missing, so lesson ids cannot be probed."""
        lesson = await self._memory.get_lesson(lesson_id)
        if lesson is None or lesson.user_id != profile_id:
            raise LessonNotFoundError
        return lesson

    async def view(self, lesson_id: str, profile_id: str) -> LessonView:
        lesson = await self._owned(lesson_id, profile_id)
        conversation = await self._tutor.conversation(lesson_id)
        clock = _clock(lesson) if lesson.status == LessonStatus.ACTIVE else None
        return LessonView(
            lesson=lesson,
            conversation=conversation,
            time_left_seconds=round(clock.remaining_seconds) if clock else None,
        )

    # --- One tutor turn ----------------------------------------------------------

    async def request_turn(
        self, lesson_id: str, profile_id: str, content: str | None
    ) -> TurnRequest:
        """Check that a turn can run. `content=None` asks the tutor to open the lesson."""
        lesson = await self._owned(lesson_id, profile_id)
        if lesson.status != LessonStatus.ACTIVE:
            raise LessonEndedError
        if self._locks[lesson_id].locked():
            raise LessonBusyError
        if content is None:
            return TurnRequest(lesson)
        if not content.strip():
            raise EmptyMessageError
        if self._moderator is not None:
            verdict = await self._moderator.check(content)
            if not verdict.allowed:
                return TurnRequest(lesson, blocked=verdict)
        return TurnRequest(lesson)

    async def run_turn(self, lesson: Lesson, content: str | None) -> AsyncIterator[TurnEvent]:
        """Run one turn under the lesson's lock and yield what happens."""
        is_kickoff = content is None
        async with self._locks[lesson.id]:
            # Checked under the lock so two simultaneous kickoffs cannot both run.
            conversation = await self._tutor.conversation(lesson.id)
            if is_kickoff and conversation.started:
                yield TurnDone()
                return
            if not is_kickoff and not conversation.started:
                yield TurnFailed("The lesson has not started yet.")
                return

            # The clock is read when the turn runs, under the lock.
            clock = None if is_kickoff else _clock(lesson)
            events = (
                self._tutor.start(lesson.id, await self._context(lesson))
                if is_kickoff
                else self._tutor.reply(lesson.id, content.strip(), clock.note() if clock else None)
            )
            try:
                async for event in events:
                    yield event
            except Exception:
                logger.exception("Tutor turn failed for lesson %s", lesson.id)
                yield TurnFailed("The tutor could not answer. Try again.")
                return
            if clock is not None and clock.phase is ClockPhase.TIME_UP:
                yield LessonTimeUp()
            yield TurnDone()

    async def _context(self, lesson: Lesson) -> LessonContext:
        """Learner context copied from long-term memory into the lesson at its start."""
        profile = await self._memory.get_profile(lesson.user_id)
        progress = await self._memory.get_progress(lesson.user_id)
        return LessonContext(
            user_id=lesson.user_id,
            profile=profile,
            topic=lesson.topic,
            progress=progress.text if progress else "",
            previous_summaries=await self._memory.recent_summaries(
                lesson.user_id, self._recent_summaries_count
            ),
            lesson_minutes=lesson.duration_minutes,
        )

    # --- Ending ------------------------------------------------------------------

    async def end(self, lesson_id: str, profile_id: str) -> Lesson:
        """End the lesson and save its summary to long-term memory. Safe to call twice."""
        await self._owned(lesson_id, profile_id)
        lock = self._locks[lesson_id]
        if lock.locked():
            raise LessonBusyError
        async with lock:
            # Re-read under the lock: a concurrent request may have ended it already.
            lesson = await self._owned(lesson_id, profile_id)
            try:
                return await self._finish(lesson)
            except Exception as error:
                logger.exception("Summarizing lesson %s failed", lesson_id)
                raise LessonSummaryError from error

    async def _finish(self, lesson: Lesson) -> Lesson:
        """Summarize a lesson into long-term memory. Ending an ended lesson is a no-op.

        A lesson where the learner never wrote anything is discarded instead of summarized.
        """
        if lesson.status != LessonStatus.ACTIVE:
            return lesson

        conversation = await self._tutor.conversation(lesson.id)
        messages = conversation.messages
        profile = await self._memory.get_profile(lesson.user_id)
        lesson.ended_at = _now()

        if profile is None or not any(message.role == "user" for message in messages):
            lesson.status = LessonStatus.DISCARDED
            await self._memory.save_lesson(lesson)
            return lesson

        lesson.summary = await self._summarizer.summarize(
            profile=profile,
            topic=lesson.topic,
            transcript=_lesson_transcript(conversation),
            mistakes=conversation.mistakes,
            vocabulary=conversation.vocabulary,
        )
        lesson.status = LessonStatus.SUMMARIZED
        await self._memory.save_lesson(lesson)

        # The lesson summary is already saved; a failed progress update must not undo it.
        try:
            previous = await self._memory.get_progress(lesson.user_id)
            text = await self._summarizer.update_progress(
                profile=profile,
                previous=previous.text if previous else "",
                date=lesson.created_at.date().isoformat(),
                topic=lesson.topic,
                summary=lesson.summary,
            )
            await self._memory.set_progress(lesson.user_id, text)
        except Exception:
            logger.exception("Progress update failed after lesson %s", lesson.id)
        return lesson

    async def end_stale(self, max_idle: timedelta) -> int:
        """End lessons that were left open (e.g. the tab was closed). Returns how many."""
        now = _now()
        ended = 0
        for lesson in await self._memory.list_active_lessons():
            conversation = await self._tutor.conversation(lesson.id)
            # A lesson's last checkpoint marks its last activity.
            last_activity = conversation.last_activity or lesson.created_at
            if now - last_activity < max_idle:
                continue
            try:
                async with self._locks[lesson.id]:
                    await self._finish(lesson)
                ended += 1
            except Exception:
                logger.exception("Could not end stale lesson %s", lesson.id)
        return ended
