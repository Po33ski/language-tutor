import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field

from app.agent.prompts import KICKOFF_MESSAGE
from app.agent.state import Mistake, VocabularyItem
from app.agent.transcript import (
    KICKOFF_ID_PREFIX,
    ChatMessage,
    thread_config,
    to_chat_messages,
)
from app.agent.wrapup import end_lesson
from app.api.deps import LessonLocksDep, SettingsDep, StoreDep, SummarizerDep, TutorDep
from app.api.security import rate_limit
from app.config import Settings
from app.storage import memory
from app.storage.memory import Lesson

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lessons", tags=["lessons"])


class LessonCreate(BaseModel):
    user_id: str
    # Defaults to the profile's main topic.
    topic: str | None = Field(default=None, max_length=200)


class LessonDetail(BaseModel):
    lesson: Lesson
    messages: list[ChatMessage]
    mistakes: list[Mistake]
    vocabulary: list[VocabularyItem]


class SendMessageRequest(BaseModel):
    # None starts the lesson: the tutor greets the learner and asks the first question.
    content: str | None = Field(default=None, max_length=4000)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _require_lesson(store: StoreDep, lesson_id: str) -> Lesson:
    lesson = await memory.get_lesson(store, lesson_id)
    if lesson is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lesson not found")
    return lesson


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_lesson(data: LessonCreate, store: StoreDep) -> Lesson:
    profile = await memory.get_profile(store, data.user_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile not found")
    topic = (data.topic or "").strip() or profile.main_topic
    return await memory.create_lesson(store, profile.id, topic)


@router.get("")
async def list_lessons(user_id: str, store: StoreDep) -> list[Lesson]:
    return await memory.list_lessons(store, user_id)


@router.get("/{lesson_id}")
async def get_lesson(lesson_id: str, store: StoreDep, tutor: TutorDep) -> LessonDetail:
    lesson = await _require_lesson(store, lesson_id)
    snapshot = await tutor.aget_state(thread_config(lesson_id))
    values = snapshot.values
    return LessonDetail(
        lesson=lesson,
        messages=to_chat_messages(values.get("messages", [])),
        mistakes=values.get("mistakes", []),
        vocabulary=values.get("vocabulary", []),
    )


async def _initial_state(store: StoreDep, settings: Settings, lesson: Lesson) -> dict:
    """Learner context copied from long-term memory into the lesson at its start."""
    profile = await memory.get_profile(store, lesson.user_id)
    progress = await memory.get_progress(store, lesson.user_id)
    return {
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


@router.post("/{lesson_id}/end", dependencies=[Depends(rate_limit)])
async def end_lesson_endpoint(
    lesson_id: str,
    store: StoreDep,
    tutor: TutorDep,
    summarizer: SummarizerDep,
    locks: LessonLocksDep,
) -> Lesson:
    """End the lesson and save its summary to long-term memory. Safe to call twice."""
    lesson = await _require_lesson(store, lesson_id)
    lock = locks[lesson_id]
    if lock.locked():
        raise HTTPException(status.HTTP_409_CONFLICT, "The tutor is still answering")
    async with lock:
        # Re-read under the lock: a concurrent request may have ended it already.
        lesson = await _require_lesson(store, lesson_id)
        try:
            return await end_lesson(store, tutor, summarizer, lesson)
        except Exception as error:
            logger.exception("Summarizing lesson %s failed", lesson_id)
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, "Could not summarize the lesson. Try again."
            ) from error


@router.post(
    "/{lesson_id}/messages",
    dependencies=[Depends(rate_limit)],
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def send_message(
    lesson_id: str,
    body: SendMessageRequest,
    store: StoreDep,
    tutor: TutorDep,
    locks: LessonLocksDep,
    settings: SettingsDep,
) -> StreamingResponse:
    """Run one tutor turn and stream it as server-sent events.

    Events: `token` {text}, `mistake` {original, corrected, explanation},
    `vocabulary` {word, meaning, example}, `error` {message}, `done` {}.
    """
    lesson = await _require_lesson(store, lesson_id)
    if lesson.status != memory.LessonStatus.ACTIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, "Lesson has already ended")
    lock = locks[lesson_id]
    if lock.locked():
        raise HTTPException(status.HTTP_409_CONFLICT, "The tutor is still answering")

    is_kickoff = body.content is None
    if not is_kickoff and not body.content.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Message is empty")
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

            inputs = (
                await _initial_state(store, settings, lesson)
                if is_kickoff
                else {"messages": [HumanMessage(body.content.strip())]}
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
