"""Ending lessons: write the summary and progress profile to long-term memory."""

import asyncio
import logging
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore

from app.agent.summarizer import Summarizer
from app.agent.transcript import format_transcript, thread_config, to_chat_messages
from app.storage import memory
from app.storage.memory import Lesson, LessonStatus

logger = logging.getLogger(__name__)


async def end_lesson(
    store: BaseStore, tutor: CompiledStateGraph, summarizer: Summarizer, lesson: Lesson
) -> Lesson:
    """Summarize a lesson into long-term memory. Ending an ended lesson is a no-op.

    A lesson where the learner never wrote anything is discarded instead of summarized.
    """
    if lesson.status != LessonStatus.ACTIVE:
        return lesson

    snapshot = await tutor.aget_state(thread_config(lesson.id))
    values = snapshot.values
    messages = to_chat_messages(values.get("messages", []))
    profile = await memory.get_profile(store, lesson.user_id)
    lesson.ended_at = datetime.now(UTC)

    if profile is None or not any(message.role == "user" for message in messages):
        lesson.status = LessonStatus.DISCARDED
        await memory.save_lesson(store, lesson)
        return lesson

    lesson.summary = await summarizer.summarize(
        profile=profile,
        topic=lesson.topic,
        transcript=format_transcript(messages),
        mistakes=values.get("mistakes", []),
        vocabulary=values.get("vocabulary", []),
    )
    lesson.status = LessonStatus.SUMMARIZED
    await memory.save_lesson(store, lesson)

    # The lesson summary is already saved; a failed progress update must not undo it.
    try:
        previous = await memory.get_progress(store, lesson.user_id)
        text = await summarizer.update_progress(
            profile=profile,
            previous=previous.text if previous else "",
            date=lesson.created_at.date().isoformat(),
            topic=lesson.topic,
            summary=lesson.summary,
        )
        await memory.set_progress(store, lesson.user_id, text)
    except Exception:
        logger.exception("Progress update failed after lesson %s", lesson.id)
    return lesson


async def end_stale_lessons(
    store: BaseStore,
    tutor: CompiledStateGraph,
    summarizer: Summarizer,
    locks: Mapping[str, asyncio.Lock],
    max_idle: timedelta,
) -> int:
    """End lessons that were left open (e.g. the tab was closed). Returns how many ended."""
    now = datetime.now(UTC)
    ended = 0
    for lesson in await memory.list_active_lessons(store):
        snapshot = await tutor.aget_state(thread_config(lesson.id))
        # A lesson's last checkpoint marks its last activity.
        last_activity = lesson.created_at
        if snapshot.created_at:
            last_activity = datetime.fromisoformat(snapshot.created_at)
        if now - last_activity < max_idle:
            continue
        try:
            async with locks[lesson.id]:
                await end_lesson(store, tutor, summarizer, lesson)
            ended += 1
        except Exception:
            logger.exception("Could not end stale lesson %s", lesson.id)
    return ended
