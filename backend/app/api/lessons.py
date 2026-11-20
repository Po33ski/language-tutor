import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field

from app.agent.clock import CLOCK_NOTE_KEY, ClockPhase, LessonClock
from app.agent.prompts import KICKOFF_MESSAGE
from app.agent.state import Mistake, VocabularyItem
from app.agent.transcript import (
    KICKOFF_ID_PREFIX,
    ChatMessage,
    thread_config,
    to_chat_messages,
)
from app.agent.wrapup import end_lesson
from app.api.deps import (
    LessonLocksDep,
    ModeratorDep,
    SettingsDep,
    StoreDep,
    SummarizerDep,
    TutorDep,
)
from app.api.security import CurrentUserDep, daily_quota, rate_limited
from app.auth.store import User
from app.config import Settings
from app.safety.moderation import BLOCKED_MESSAGES
from app.storage import memory
from app.storage.memory import Lesson

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lessons", tags=["lessons"])


class LessonCreate(BaseModel):
    # Defaults to the profile's main topic.
    topic: str | None = Field(default=None, max_length=200)


class LessonDetail(BaseModel):
    lesson: Lesson
    messages: list[ChatMessage]
    mistakes: list[Mistake]
    vocabulary: list[VocabularyItem]
    # Seconds left on the lesson clock, measured by the server (so a wrong device clock
    # does not matter); None for ended lessons and lessons without a planned length.
    time_left_seconds: int | None = None


class SendMessageRequest(BaseModel):
    # None starts the lesson: the tutor greets the learner and asks the first question.
    content: str | None = Field(default=None, max_length=4000)


def _now() -> datetime:
    return datetime.now(UTC)


def _clock(lesson: Lesson) -> LessonClock | None:
    if lesson.duration_minutes is None:
        return None
    return LessonClock.at(lesson.created_at, lesson.duration_minutes, _now())


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _require_lesson(store: StoreDep, lesson_id: str, user: User) -> Lesson:
    """The lesson if it belongs to the signed-in user. Someone else's lesson is reported as
    missing (404, not 403), so lesson ids cannot be probed."""
    lesson = await memory.get_lesson(store, lesson_id)
    if lesson is None or lesson.user_id != user.profile_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lesson not found")
    return lesson


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_lesson(data: LessonCreate, user: CurrentUserDep, store: StoreDep) -> Lesson:
    profile = await memory.get_profile(store, user.profile_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Create your profile first")
    topic = (data.topic or "").strip() or profile.main_topic
    return await memory.create_lesson(store, profile.id, topic, profile.lesson_minutes)


@router.get("")
async def list_lessons(user: CurrentUserDep, store: StoreDep) -> list[Lesson]:
    """The signed-in user's lessons, newest first."""
    return await memory.list_lessons(store, user.profile_id)


@router.get("/{lesson_id}")
async def get_lesson(
    lesson_id: str, user: CurrentUserDep, store: StoreDep, tutor: TutorDep
) -> LessonDetail:
    lesson = await _require_lesson(store, lesson_id, user)
    snapshot = await tutor.aget_state(thread_config(lesson_id))
    values = snapshot.values
    clock = _clock(lesson) if lesson.status == memory.LessonStatus.ACTIVE else None
    return LessonDetail(
        lesson=lesson,
        messages=to_chat_messages(values.get("messages", [])),
        mistakes=values.get("mistakes", []),
        vocabulary=values.get("vocabulary", []),
        time_left_seconds=round(clock.remaining_seconds) if clock else None,
    )


async def _initial_state(store: StoreDep, settings: Settings, lesson: Lesson) -> dict:
    """Learner context copied from long-term memory into the lesson at its start."""
    profile = await memory.get_profile(store, lesson.user_id)
    progress = await memory.get_progress(store, lesson.user_id)
    state = {
        "user_id": lesson.user_id,
        "profile": profile.model_dump(mode="json") if profile else {},
        "topic": lesson.topic,
        "progress": progress.text if progress else "",
        "previous_summaries": await memory.recent_summaries(
            store, lesson.user_id, settings.recent_summaries_count
        ),
        "mistakes": [],
        "vocabulary": [],
        "messages": [HumanMessage(KICKOFF_MESSAGE, id=f"{KICKOFF_ID_PREFIX}{lesson.id}")],
    }
    if lesson.duration_minutes is not None:
        state["lesson_minutes"] = lesson.duration_minutes
    return state


def _learner_message(content: str, clock: LessonClock | None) -> HumanMessage:
    """The learner's message, with the lesson clock note for the tutor (if timed)."""
    if clock is None:
        return HumanMessage(content)
    return HumanMessage(content, additional_kwargs={CLOCK_NOTE_KEY: clock.note()})


@router.post("/{lesson_id}/end", dependencies=[Depends(rate_limited("tutor"))])
async def end_lesson_endpoint(
    lesson_id: str,
    user: CurrentUserDep,
    store: StoreDep,
    tutor: TutorDep,
    summarizer: SummarizerDep,
    locks: LessonLocksDep,
) -> Lesson:
    """End the lesson and save its summary to long-term memory. Safe to call twice."""
    lesson = await _require_lesson(store, lesson_id, user)
    lock = locks[lesson_id]
    if lock.locked():
        raise HTTPException(status.HTTP_409_CONFLICT, "The tutor is still answering")
    async with lock:
        # Re-read under the lock: a concurrent request may have ended it already.
        lesson = await _require_lesson(store, lesson_id, user)
        try:
            return await end_lesson(store, tutor, summarizer, lesson)
        except Exception as error:
            logger.exception("Summarizing lesson %s failed", lesson_id)
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, "Could not summarize the lesson. Try again."
            ) from error


@router.post(
    "/{lesson_id}/messages",
    dependencies=[Depends(rate_limited("tutor")), Depends(daily_quota("tutor_turn"))],
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def send_message(
    lesson_id: str,
    body: SendMessageRequest,
    user: CurrentUserDep,
    store: StoreDep,
    tutor: TutorDep,
    locks: LessonLocksDep,
    settings: SettingsDep,
    moderator: ModeratorDep,
) -> StreamingResponse:
    """Run one tutor turn and stream it as server-sent events.

    Events: `token` {text}, `mistake` {original, corrected, explanation},
    `vocabulary` {word, meaning, example}, `time_up` {} (this reply was the tutor's
    closing message: the lesson's time is over, so the client ends the lesson),
    `blocked` {message, category} (moderation stopped the learner's message: the tutor
    never saw it and it is not part of the lesson), `error` {message}, `done` {}.
    """
    lesson = await _require_lesson(store, lesson_id, user)
    if lesson.status != memory.LessonStatus.ACTIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, "Lesson has already ended")
    lock = locks[lesson_id]
    if lock.locked():
        raise HTTPException(status.HTTP_409_CONFLICT, "The tutor is still answering")

    is_kickoff = body.content is None
    if not is_kickoff and not body.content.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Message is empty")
    if not is_kickoff and moderator is not None:
        verdict = await moderator.check(body.content)
        if not verdict.allowed:
            # The text itself is not logged: category and scores are enough to review.
            logger.warning(
                "Blocked a message in lesson %s (account %s): %s %s",
                lesson_id,
                user.id,
                verdict.category,
                {label: round(score, 2) for label, score in verdict.scores.items()},
            )
            blocked = {"message": BLOCKED_MESSAGES[verdict.category], "category": verdict.category}
            events = [_sse("blocked", blocked), _sse("done", {})]
            return StreamingResponse(iter(events), media_type="text/event-stream")
    config = thread_config(lesson_id)

    async def stream() -> AsyncIterator[str]:
        async with lock:
            # Checked under the lock so two simultaneous kickoffs cannot both run.
            snapshot = await tutor.aget_state(config)
            started = bool(snapshot.values.get("messages"))
            if is_kickoff and started:
                yield _sse("done", {})
                return
            if not is_kickoff and not started:
                yield _sse("error", {"message": "The lesson has not started yet."})
                return

            # The clock is read when the turn runs, under the lock.
            clock = None if is_kickoff else _clock(lesson)
            inputs = (
                await _initial_state(store, settings, lesson)
                if is_kickoff
                else {"messages": [_learner_message(body.content.strip(), clock)]}
            )
            try:
                async for mode, data in tutor.astream(
                    inputs, config, stream_mode=["messages", "updates"]
                ):
                    for event in _events_from_chunk(mode, data):
                        yield event
            except Exception:
                logger.exception("Tutor turn failed for lesson %s", lesson_id)
                yield _sse("error", {"message": "The tutor could not answer. Try again."})
                return
            if clock is not None and clock.phase is ClockPhase.TIME_UP:
                yield _sse("time_up", {})
            yield _sse("done", {})

    return StreamingResponse(stream(), media_type="text/event-stream")


def _events_from_chunk(mode: str, data) -> list[str]:
    if mode == "messages":
        chunk, metadata = data
        # Streaming models emit AIMessageChunks; non-streaming ones emit one AIMessage.
        if metadata.get("langgraph_node") == "model" and isinstance(chunk, AIMessage):
            if chunk.text:
                return [_sse("token", {"text": chunk.text})]
        return []

    # mode == "updates": surface items recorded by the tutor's tools.
    events = []
    for node, update in data.items():
        if node != "tools" or not update:
            continue
        updates = update if isinstance(update, list) else [update]
        for item in updates:
            if not isinstance(item, dict):
                continue
            events += [_sse("mistake", dict(m)) for m in item.get("mistakes", [])]
            events += [_sse("vocabulary", dict(v)) for v in item.get("vocabulary", [])]
    return events
