"""Runs a case through the app's real lesson code, on a throwaway data directory."""

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage

from app.config import Settings
from app.domain.learners.models import ProfileCreate
from app.domain.lessons.models import LessonTimeUp, TurnFailed
from app.domain.lessons.service import LessonService
from app.infra.agent.graph import build_tutor_agent
from app.infra.agent.prompts import build_system_prompt
from app.infra.agent.transcript import thread_config
from app.infra.agent.tutor import LangGraphTutor
from app.infra.persistence.connections import open_persistence
from app.infra.persistence.learner_memory import LearnerMemoryStore
from evals.schema import Case, CaseRun, ToolCall, Turn


class HarnessError(Exception):
    """The turn failed in the app or the API; this is not a graded failure of the tutor."""


class _UnusedSummarizer:
    """Evals grade lesson turns and never end a lesson."""

    async def summarize(self, **kwargs):
        raise NotImplementedError

    async def update_progress(self, **kwargs):
        raise NotImplementedError


def _add_usage(total: dict[str, int], message: AIMessage) -> None:
    usage = message.usage_metadata or {}
    details = usage.get("input_token_details") or {}
    for key, value in (
        ("input_tokens", usage.get("input_tokens", 0)),
        ("output_tokens", usage.get("output_tokens", 0)),
        ("cache_read_input_tokens", details.get("cache_read", 0)),
        ("cache_creation_input_tokens", details.get("cache_creation", 0)),
    ):
        total[key] = total.get(key, 0) + (value or 0)


async def run_case(case: Case, model: BaseChatModel) -> CaseRun:
    with tempfile.TemporaryDirectory(prefix="tutor-eval-") as data_dir:
        settings = Settings(data_dir=Path(data_dir))
        async with open_persistence(settings) as persistence:
            return await _run(case, model, persistence)


async def _run(case: Case, model: BaseChatModel, persistence) -> CaseRun:
    graph = build_tutor_agent(model, persistence.checkpointer, persistence.store)
    memory = LearnerMemoryStore(persistence.store)
    lessons = LessonService(memory, LangGraphTutor(graph), _UnusedSummarizer(), None, 3)
    profile = await memory.create_profile(
        ProfileCreate(
            name="Sam",
            level=case.level,
            main_topic=case.topic,
            goal="Get a better job",
            preferences=dict(case.preferences),
            lesson_minutes=case.minutes,
        )
    )
    lesson = await memory.create_lesson(profile.id, case.topic, case.minutes)

    async def turn(content: str | None) -> bool:
        time_up = False
        async for event in lessons.run_turn(lesson, content):
            if isinstance(event, TurnFailed):
                raise HarnessError(event.message)
            time_up = time_up or isinstance(event, LessonTimeUp)
        return time_up

    config = thread_config(lesson.id)
    await turn(None)
    # The clock counts from the lesson's start, so moving the start moves the clock.
    lesson.created_at = datetime.now(UTC) - timedelta(minutes=case.elapsed_minutes)

    turns: list[Turn] = []
    time_up = False
    seen = len((await graph.aget_state(config)).values["messages"])
    for text in case.turns:
        time_up = await turn(text)
        messages = (await graph.aget_state(config)).values["messages"]
        new = [m for m in messages[seen:] if isinstance(m, AIMessage)]
        seen = len(messages)
        turns.append(
            Turn(
                learner=text,
                reply="".join(m.text for m in new),
                tool_calls=tuple(
                    ToolCall(call["name"], dict(call["args"])) for m in new for call in m.tool_calls
                ),
            )
        )

    state = await graph.aget_state(config)
    answers = [m for m in state.values["messages"] if isinstance(m, AIMessage)]
    usage: dict[str, int] = {}
    for message in answers:
        _add_usage(usage, message)
    metadata = answers[-1].response_metadata
    return CaseRun(
        turns=turns,
        system_prompt=build_system_prompt(state.values),
        time_up=time_up,
        stop_reason=metadata.get("stop_reason"),
        model=metadata.get("model_name") or metadata.get("model"),
        usage=usage,
    )
