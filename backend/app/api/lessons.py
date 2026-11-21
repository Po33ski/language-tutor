import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.deps import LessonsDep
from app.api.security import CurrentUserDep, daily_quota, rate_limited
from app.domain.lessons.models import (
    ChatMessage,
    EmptyMessageError,
    Lesson,
    LessonBusyError,
    LessonEndedError,
    LessonNotFoundError,
    LessonSummaryError,
    LessonTimeUp,
    Mistake,
    MistakeRecorded,
    ProfileRequiredError,
    TurnDone,
    TurnEvent,
    TurnFailed,
    TutorToken,
    VocabularyAdded,
    VocabularyItem,
)
from app.domain.moderation.policy import BLOCKED_MESSAGES

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


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _sse_from_event(event: TurnEvent) -> str:
    match event:
        case TutorToken(text=text):
            return _sse("token", {"text": text})
        case MistakeRecorded(mistake=mistake):
            return _sse("mistake", dict(mistake))
        case VocabularyAdded(item=item):
            return _sse("vocabulary", dict(item))
        case TurnFailed(message=message):
            return _sse("error", {"message": message})
        case LessonTimeUp():
            return _sse("time_up", {})
        case TurnDone():
            return _sse("done", {})
    raise TypeError(f"Unknown turn event: {event!r}")


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Lesson not found")


def _busy() -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, "The tutor is still answering")


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_lesson(data: LessonCreate, user: CurrentUserDep, lessons: LessonsDep) -> Lesson:
    try:
        return await lessons.create(user.profile_id, data.topic)
    except ProfileRequiredError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Create your profile first") from error


@router.get("")
async def list_lessons(user: CurrentUserDep, lessons: LessonsDep) -> list[Lesson]:
    """The signed-in user's lessons, newest first."""
    return await lessons.list_for_learner(user.profile_id)


@router.get("/{lesson_id}")
async def get_lesson(lesson_id: str, user: CurrentUserDep, lessons: LessonsDep) -> LessonDetail:
    try:
        view = await lessons.view(lesson_id, user.profile_id)
    except LessonNotFoundError as error:
        raise _not_found() from error
    return LessonDetail(
        lesson=view.lesson,
        messages=view.conversation.messages,
        mistakes=view.conversation.mistakes,
        vocabulary=view.conversation.vocabulary,
        time_left_seconds=view.time_left_seconds,
    )


@router.post("/{lesson_id}/end", dependencies=[Depends(rate_limited("tutor"))])
async def end_lesson_endpoint(lesson_id: str, user: CurrentUserDep, lessons: LessonsDep) -> Lesson:
    """End the lesson and save its summary to long-term memory. Safe to call twice."""
    try:
        return await lessons.end(lesson_id, user.profile_id)
    except LessonNotFoundError as error:
        raise _not_found() from error
    except LessonBusyError as error:
        raise _busy() from error
    except LessonSummaryError as error:
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
    lessons: LessonsDep,
) -> StreamingResponse:
    """Run one tutor turn and stream it as server-sent events.

    Events: `token` {text}, `mistake` {original, corrected, explanation},
    `vocabulary` {word, meaning, example}, `time_up` {} (this reply was the tutor's
    closing message: the lesson's time is over, so the client ends the lesson),
    `blocked` {message, category} (moderation stopped the learner's message: the tutor
    never saw it and it is not part of the lesson), `error` {message}, `done` {}.
    """
    try:
        turn = await lessons.request_turn(lesson_id, user.profile_id, body.content)
    except LessonNotFoundError as error:
        raise _not_found() from error
    except LessonEndedError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, "Lesson has already ended") from error
    except LessonBusyError as error:
        raise _busy() from error
    except EmptyMessageError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Message is empty") from error

    if turn.blocked is not None:
        verdict = turn.blocked
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

    async def stream() -> AsyncIterator[str]:
        async for event in lessons.run_turn(turn.lesson, body.content):
            yield _sse_from_event(event)

    return StreamingResponse(stream(), media_type="text/event-stream")
