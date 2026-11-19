from langchain_core.messages import AIMessage

from tests.conftest import mistake_call, parse_sse


def _start_lesson(client, profile_payload) -> str:
    assert client.post("/api/profile", json=profile_payload).status_code == 201
    return client.post("/api/lessons", json={}).json()["id"]


def _send(client, lesson_id: str, content: str | None) -> list[tuple[str, dict]]:
    response = client.post(f"/api/lessons/{lesson_id}/messages", json={"content": content})
    assert response.status_code == 200
    return parse_sse(response.text)


def _text(events) -> str:
    return "".join(data["text"] for event, data in events if event == "token")


def test_profile_is_created_once_per_account(make_client, profile_payload) -> None:
    client = make_client([])
    assert client.get("/api/profile").status_code == 404
    assert client.get("/api/auth/me").json()["has_profile"] is False
    created = client.post("/api/profile", json=profile_payload)
    assert created.status_code == 201
    profile = created.json()
    assert client.get("/api/profile").json() == profile
    assert client.get("/api/auth/me").json()["has_profile"] is True
    assert client.post("/api/profile", json=profile_payload).status_code == 409


def test_lesson_topic_defaults_to_main_topic(make_client, profile_payload) -> None:
    client = make_client([])
    assert client.post("/api/lessons", json={}).status_code == 404  # no profile yet
    client.post("/api/profile", json=profile_payload)
    lesson = client.post("/api/lessons", json={}).json()
    assert lesson["topic"] == "Job interview preparation"
    assert lesson["status"] == "active"
    assert client.get("/api/lessons").json() == [lesson]


def test_lesson_conversation_with_mistake(make_client, profile_payload) -> None:
    client = make_client(
        [
            AIMessage("Hi Anna! Tell me about yourself."),
            mistake_call("I am work", "I work", "Use the present simple."),
            AIMessage("Good! Say 'I work as a developer'. What do you do?"),
        ]
    )
    lesson_id = _start_lesson(client, profile_payload)

    kickoff = _send(client, lesson_id, None)
    assert _text(kickoff) == "Hi Anna! Tell me about yourself."
    assert kickoff[-1] == ("done", {})

    turn = _send(client, lesson_id, "I am work as developer")
    mistake = {
        "original": "I am work",
        "corrected": "I work",
        "explanation": "Use the present simple.",
    }
    assert ("mistake", mistake) in turn
    assert _text(turn) == "Good! Say 'I work as a developer'. What do you do?"

    detail = client.get(f"/api/lessons/{lesson_id}").json()
    # The hidden kickoff signal and tool messages are not part of the visible chat.
    assert [m["role"] for m in detail["messages"]] == ["assistant", "user", "assistant"]
    assert detail["messages"][1]["content"] == "I am work as developer"
    assert detail["mistakes"] == [mistake]


def test_second_kickoff_does_not_restart_lesson(make_client, profile_payload) -> None:
    client = make_client([AIMessage("Hi Anna!")])
    lesson_id = _start_lesson(client, profile_payload)
    _send(client, lesson_id, None)

    assert _send(client, lesson_id, None) == [("done", {})]
    assert len(client.get(f"/api/lessons/{lesson_id}").json()["messages"]) == 1


def test_message_before_kickoff_is_rejected(make_client, profile_payload) -> None:
    client = make_client([])
    lesson_id = _start_lesson(client, profile_payload)
    events = _send(client, lesson_id, "Hello")
    assert events[0][0] == "error"


def test_empty_message_and_unknown_lesson(make_client, profile_payload) -> None:
    client = make_client([])
    lesson_id = _start_lesson(client, profile_payload)
    empty = client.post(f"/api/lessons/{lesson_id}/messages", json={"content": "   "})
    assert empty.status_code == 422
    unknown = client.post("/api/lessons/missing/messages", json={"content": "Hi"})
    assert unknown.status_code == 404


def test_reply_written_with_tool_calls_is_not_repeated(make_client, profile_payload) -> None:
    reply_with_tools = mistake_call("I am work", "I work", "Use the present simple.")
    reply_with_tools.content = "Small fix: we say 'I work'. What do you do?"
    client = make_client(
        [
            AIMessage("Hi Anna!"),
            reply_with_tools,
            # Must only be used for the next turn, not as a repeated reply.
            AIMessage("Next turn reply."),
        ]
    )
    lesson_id = _start_lesson(client, profile_payload)
    _send(client, lesson_id, None)

    turn = _send(client, lesson_id, "I am work as developer")
    assert _text(turn) == "Small fix: we say 'I work'. What do you do?"
    assert _text(_send(client, lesson_id, "I build APIs")) == "Next turn reply."
