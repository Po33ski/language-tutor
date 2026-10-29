from datetime import timedelta

from langchain_core.messages import AIMessage

from app.agent.wrapup import end_stale_lessons
from tests.test_lessons import _send, _start_lesson


def _lesson_with_learner_message(client, profile_payload) -> str:
    lesson_id = _start_lesson(client, profile_payload)
    _send(client, lesson_id, None)
    _send(client, lesson_id, "I am work as developer")
    return lesson_id


def test_end_lesson_saves_summary_and_progress(make_client, profile_payload, summarizer) -> None:
    client = make_client([AIMessage("Hi Anna! Tell me about you."), AIMessage("Nice!")])
    lesson_id = _lesson_with_learner_message(client, profile_payload)

    response = client.post(f"/api/lessons/{lesson_id}/end")
    assert response.status_code == 200
    lesson = response.json()
    assert lesson["status"] == "summarized"
    assert lesson["ended_at"] is not None
    assert lesson["summary"]["summary"] == "You introduced yourself."

    # The summarizer saw the visible transcript, without the hidden kickoff message.
    transcript = summarizer.summarize_calls[0]["transcript"]
    assert transcript.startswith("Tutor: Hi Anna!")
    assert "Learner: I am work as developer" in transcript
    assert "START_LESSON" not in transcript

    progress = client.get(f"/api/profiles/{lesson['user_id']}/progress").json()
    assert progress["text"] == "Progress after 1 lesson(s)."

    # Ending again is a no-op, and the ended lesson accepts no more messages.
    assert client.post(f"/api/lessons/{lesson_id}/end").json() == lesson
    assert len(summarizer.summarize_calls) == 1
    blocked = client.post(f"/api/lessons/{lesson_id}/messages", json={"content": "Hi"})
    assert blocked.status_code == 409


def test_progress_builds_on_previous_lessons(make_client, profile_payload, summarizer) -> None:
    client = make_client([AIMessage("Hi!"), AIMessage("Good."), AIMessage("Hi!"), AIMessage("Ok.")])
    first = _lesson_with_learner_message(client, profile_payload)
    client.post(f"/api/lessons/{first}/end")
    user_id = client.get(f"/api/lessons/{first}").json()["lesson"]["user_id"]

    second = client.post("/api/lessons", json={"user_id": user_id}).json()["id"]
    _send(client, second, None)
    _send(client, second, "Hello again")
    client.post(f"/api/lessons/{second}/end")

    assert summarizer.progress_calls[1]["previous"] == "Progress after 1 lesson(s)."


def test_lesson_without_learner_messages_is_discarded(
    make_client, profile_payload, summarizer
) -> None:
    client = make_client([AIMessage("Hi Anna!")])
    lesson_id = _start_lesson(client, profile_payload)
    _send(client, lesson_id, None)

    lesson = client.post(f"/api/lessons/{lesson_id}/end").json()
    assert lesson["status"] == "discarded"
    assert lesson["summary"] is None
    assert summarizer.summarize_calls == []


def test_failed_summary_keeps_lesson_active(make_client, profile_payload, summarizer) -> None:
    client = make_client([AIMessage("Hi!"), AIMessage("Good.")])
    lesson_id = _lesson_with_learner_message(client, profile_payload)
    summarizer.fail = True

    assert client.post(f"/api/lessons/{lesson_id}/end").status_code == 502
    assert client.get(f"/api/lessons/{lesson_id}").json()["lesson"]["status"] == "active"


def test_stale_lessons_are_ended(make_client, profile_payload, summarizer) -> None:
    client = make_client([AIMessage("Hi!"), AIMessage("Good.")])
    lesson_id = _lesson_with_learner_message(client, profile_payload)
    state = client.app.state

    async def sweep(max_idle: timedelta) -> int:
        return await end_stale_lessons(
            state.persistence.store, state.tutor, state.summarizer, state.lesson_locks, max_idle
        )

    # A recently active lesson is left alone; an idle one is summarized.
    assert client.portal.call(sweep, timedelta(hours=1)) == 0
    assert client.portal.call(sweep, timedelta(0)) == 1
    assert client.get(f"/api/lessons/{lesson_id}").json()["lesson"]["status"] == "summarized"
