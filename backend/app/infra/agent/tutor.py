"""The tutor as the domain sees it: LangGraph threads and streams stay behind this class."""

from collections.abc import AsyncIterator
from datetime import datetime

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph.state import CompiledStateGraph

from app.domain.lessons.models import (
    LessonContext,
    LessonConversation,
    MistakeRecorded,
    TutorEvent,
    TutorToken,
    VocabularyAdded,
)
from app.infra.agent.clock_notes import CLOCK_NOTE_KEY
from app.infra.agent.prompts import KICKOFF_MESSAGE
from app.infra.agent.transcript import KICKOFF_ID_PREFIX, thread_config, to_chat_messages


def initial_state(lesson_id: str, context: LessonContext) -> dict:
    state = {
        "user_id": context.user_id,
        "profile": context.profile.model_dump(mode="json") if context.profile else {},
        "topic": context.topic,
        "progress": context.progress,
        "previous_summaries": context.previous_summaries,
        "mistakes": [],
        "vocabulary": [],
        "messages": [HumanMessage(KICKOFF_MESSAGE, id=f"{KICKOFF_ID_PREFIX}{lesson_id}")],
    }
    if context.lesson_minutes is not None:
        state["lesson_minutes"] = context.lesson_minutes
    return state


def learner_message(text: str, clock_note: str | None) -> HumanMessage:
    """The learner's message, with the lesson clock note for the tutor (if timed)."""
    if clock_note is None:
        return HumanMessage(text)
    return HumanMessage(text, additional_kwargs={CLOCK_NOTE_KEY: clock_note})


def events_from_chunk(mode: str, data) -> list[TutorEvent]:
    if mode == "messages":
        chunk, metadata = data
        # Streaming models emit AIMessageChunks; non-streaming ones emit one AIMessage.
        if metadata.get("langgraph_node") == "model" and isinstance(chunk, AIMessage):
            if chunk.text:
                return [TutorToken(chunk.text)]
        return []

    # mode == "updates": surface items recorded by the tutor's tools.
    events: list[TutorEvent] = []
    for node, update in data.items():
        if node != "tools" or not update:
            continue
        updates = update if isinstance(update, list) else [update]
        for item in updates:
            if not isinstance(item, dict):
                continue
            events += [MistakeRecorded(m) for m in item.get("mistakes", [])]
            events += [VocabularyAdded(v) for v in item.get("vocabulary", [])]
    return events


class LangGraphTutor:
    def __init__(self, graph: CompiledStateGraph) -> None:
        self._graph = graph

    async def conversation(self, lesson_id: str) -> LessonConversation:
        snapshot = await self._graph.aget_state(thread_config(lesson_id))
        values = snapshot.values
        messages = values.get("messages", [])
        return LessonConversation(
            started=bool(messages),
            messages=to_chat_messages(messages),
            mistakes=values.get("mistakes", []),
            vocabulary=values.get("vocabulary", []),
            last_activity=(
                datetime.fromisoformat(snapshot.created_at) if snapshot.created_at else None
            ),
            earlier_summary=values.get("earlier_summary", ""),
            recent_messages=to_chat_messages(messages[values.get("compacted_messages", 0) :]),
        )

    def start(self, lesson_id: str, context: LessonContext) -> AsyncIterator[TutorEvent]:
        return self._stream(lesson_id, initial_state(lesson_id, context))

    def reply(self, lesson_id: str, text: str, clock_note: str | None) -> AsyncIterator[TutorEvent]:
        return self._stream(lesson_id, {"messages": [learner_message(text, clock_note)]})

    async def _stream(self, lesson_id: str, inputs: dict) -> AsyncIterator[TutorEvent]:
        async for mode, data in self._graph.astream(
            inputs, thread_config(lesson_id), stream_mode=["messages", "updates"]
        ):
            for event in events_from_chunk(mode, data):
                yield event
