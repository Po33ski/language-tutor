"""Long lessons: the model gets a summary of the oldest turns, the saved lesson stays whole."""

import asyncio

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.config import Settings
from app.domain.learners.models import ProfileCreate
from app.domain.lessons.models import TutorToken
from app.domain.lessons.service import LessonService
from app.infra.agent.compaction import (
    LessonCompaction,
    build_compaction,
    compacted_view,
    estimated_input_tokens,
    find_cut,
)
from app.infra.agent.graph import build_tutor_agent
from app.infra.agent.transcript import thread_config
from app.infra.agent.tutor import LangGraphTutor
from app.infra.persistence.connections import open_persistence
from app.infra.persistence.learner_memory import LearnerMemoryStore
from tests.conftest import FakeSummarizer, FakeTutorModel, mistake_call
from tests.test_lessons import _send, _start_lesson

TURN_ONE = "TURN-ONE " + "word " * 40
TURN_TWO = "TURN-TWO " + "word " * 40
SUMMARY = "SUMMARY-OF-THE-START"


def _tutor(*replies: str) -> FakeTutorModel:
    return FakeTutorModel(messages=iter([AIMessage(reply) for reply in replies]))


def _summarizer() -> GenericFakeChatModel:
    return GenericFakeChatModel(messages=iter([AIMessage(SUMMARY)]))


class BrokenModel(FakeTutorModel):
    async def ainvoke(self, *args, **kwargs):
        raise RuntimeError("model unavailable")


def _run_lesson(tmp_path, model, compaction, turns, end=False) -> dict:
    async def scenario() -> dict:
        settings = Settings(data_dir=tmp_path, anthropic_api_key="test")
        async with open_persistence(settings) as persistence:
            graph = build_tutor_agent(
                model, persistence.checkpointer, persistence.store, compaction=compaction
            )
            memory = LearnerMemoryStore(persistence.store)
            summarizer = FakeSummarizer()
            lessons = LessonService(memory, LangGraphTutor(graph), summarizer, None, 3)
            profile = await memory.create_profile(
                ProfileCreate(name="Sam", level="B1", main_topic="Interviews")
            )
            lesson = await memory.create_lesson(profile.id, "Interviews", 15)
            tokens = []
            for content in [None, *turns]:
                async for event in lessons.run_turn(lesson, content):
                    if isinstance(event, TutorToken):
                        tokens.append(event.text)
            state = (await graph.aget_state(thread_config(lesson.id))).values
            conversation = await LangGraphTutor(graph).conversation(lesson.id)
            if end:
                await lessons.end(lesson.id, profile.id)
            return {
                "tokens": "".join(tokens),
                "state": state,
                "conversation": conversation,
                "summarizer": summarizer,
            }

    return asyncio.run(scenario())


def _texts(messages) -> str:
    return "\n".join(str(message.content) for message in messages)


def test_estimate_uses_the_last_calls_real_size() -> None:
    usage = {"input_tokens": 5000, "output_tokens": 10, "total_tokens": 5010}
    messages = [HumanMessage("Hi"), AIMessage("Hello", usage_metadata=usage), HumanMessage("Ok")]
    assert 5000 < estimated_input_tokens(messages) < 5100


def test_estimate_without_usage_counts_the_text() -> None:
    assert estimated_input_tokens([HumanMessage("x" * 400)]) >= 100


def test_cut_never_separates_a_tool_call_from_its_result() -> None:
    call = {"name": "record_mistake", "args": {}, "id": "1"}
    messages = [
        HumanMessage("start"),
        AIMessage("hi"),
        HumanMessage("first " * 20),
        AIMessage("", tool_calls=[call]),
        ToolMessage("ok", tool_call_id="1"),
        AIMessage("reply"),
        HumanMessage("current"),
    ]
    assert find_cut(messages, 0, 1) == 6
    assert find_cut(messages, 0, 100) == 2
    assert isinstance(messages[find_cut(messages, 0, 100)], HumanMessage)
    # Nothing new to summarize.
    assert find_cut(messages, 6, 1000) is None


def test_view_replaces_only_the_oldest_messages() -> None:
    messages = [HumanMessage("old"), AIMessage("old reply"), HumanMessage("new")]
    assert compacted_view(messages, {}) is messages
    view = compacted_view(messages, {"compacted_messages": 2, "earlier_summary": SUMMARY})
    assert len(view) == 2
    assert SUMMARY in view[0].content
    assert view[1].content == "new"


def test_keep_must_be_below_the_trigger() -> None:
    with pytest.raises(ValueError):
        LessonCompaction(_summarizer(), 100, 100)


def test_compaction_can_be_turned_off() -> None:
    settings = Settings(anthropic_api_key="test", lesson_compact_tokens=0)
    assert build_compaction(settings) is None


def test_short_lesson_is_not_compacted(tmp_path) -> None:
    model = _tutor("Hi Sam!", "Reply one.", "Reply two.")
    compaction = LessonCompaction(BrokenModel(messages=iter([])), 30_000, 10_000)
    result = _run_lesson(tmp_path, model, compaction, [TURN_ONE, TURN_TWO])
    assert "compacted_messages" not in result["state"]
    assert "TURN-ONE" in _texts(model.inputs[-1])
    assert "Summary of the earlier part" not in _texts(model.inputs[-1])


def test_long_lesson_sends_a_summary_and_keeps_the_transcript(tmp_path) -> None:
    model = _tutor("Hi Sam!", "Reply one.", "Reply two.")
    compaction = LessonCompaction(_summarizer(), 90, 70)
    result = _run_lesson(tmp_path, model, compaction, [TURN_ONE, TURN_TWO])

    sent = _texts(model.inputs[-1])
    assert SUMMARY in sent
    assert "TURN-TWO" in sent
    assert "TURN-ONE" not in sent
    assert "[START_LESSON]" not in _texts(model.inputs[-1][1:])

    # The saved lesson is whole, and the summary never reaches the learner.
    assert [m.role for m in result["conversation"].messages] == [
        "assistant",
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert "TURN-ONE" in _texts(result["state"]["messages"])
    assert SUMMARY not in result["tokens"]
    assert not any(SUMMARY in m.content for m in result["conversation"].messages)


def test_summary_receives_recorded_corrections(tmp_path) -> None:
    class RecordingSummarizer(FakeTutorModel):
        pass

    summarizer = RecordingSummarizer(messages=iter([AIMessage(SUMMARY)]))
    model = FakeTutorModel(
        messages=iter(
            [
                AIMessage("Hi Sam!"),
                mistake_call("I am work", "I work", "Use the simple present."),
                AIMessage("Small fix."),
                AIMessage("Reply two."),
            ]
        )
    )
    compaction = LessonCompaction(summarizer, 90, 70)
    _run_lesson(tmp_path, model, compaction, [TURN_ONE, TURN_TWO])
    prompt = summarizer.inputs[0][1].content
    assert "I am work -> I work" in prompt
    assert "TURN-ONE" in prompt


def test_failed_summary_does_not_cost_the_learner_a_reply(tmp_path) -> None:
    model = _tutor("Hi Sam!", "Reply one.", "Reply two.")
    compaction = LessonCompaction(BrokenModel(messages=iter([])), 90, 70)
    result = _run_lesson(tmp_path, model, compaction, [TURN_ONE, TURN_TWO])
    assert "Reply two." in result["tokens"]
    assert "compacted_messages" not in result["state"]
    assert "TURN-ONE" in _texts(model.inputs[-1])


def test_end_of_lesson_summary_uses_the_compacted_history(tmp_path) -> None:
    model = _tutor("Hi Sam!", "Reply one.", "Reply two.")
    compaction = LessonCompaction(_summarizer(), 90, 70)
    result = _run_lesson(tmp_path, model, compaction, [TURN_ONE, TURN_TWO], end=True)
    transcript = result["summarizer"].summarize_calls[0]["transcript"]
    assert SUMMARY in transcript
    assert "TURN-TWO" in transcript
    assert "TURN-ONE" not in transcript


def test_app_compacts_and_still_shows_the_whole_lesson(make_client, profile_payload) -> None:
    client = make_client(
        [
            AIMessage("Hi Anna!"),
            AIMessage("Reply one."),
            AIMessage(SUMMARY),
            AIMessage("Reply two."),
        ],
        lesson_compact_tokens=90,
        lesson_keep_tokens=70,
    )
    lesson_id = _start_lesson(client, profile_payload)
    _send(client, lesson_id, None)
    _send(client, lesson_id, TURN_ONE)
    turn = _send(client, lesson_id, TURN_TWO)

    assert "".join(data["text"] for event, data in turn if event == "token") == "Reply two."
    assert "TURN-ONE" not in _texts(client.model.inputs[-1])
    detail = client.get(f"/api/lessons/{lesson_id}").json()
    users = [m["content"] for m in detail["messages"] if m["role"] == "user"]
    assert users == [TURN_ONE.strip(), TURN_TWO.strip()]
