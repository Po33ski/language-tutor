from langchain_core.messages import AIMessage

from tests.conftest import mistake_call, parse_sse


def _start_lesson(client, profile_payload) -> str:
    user_id = client.post("/api/profiles", json=profile_payload).json()["id"]
    return client.post("/api/lessons", json={"user_id": user_id}).json()["id"]


def _send(client, lesson_id: str, content: str | None) -> list[tuple[str, dict]]:
    response = client.post(f"/api/lessons/{lesson_id}/messages", json={"content": content})
    assert response.status_code == 200
    return parse_sse(response.text)


def _text(events) -> str:
    return "".join(data["text"] for event, data in events if event == "token")


def test_profiles_crud(make_client, profile_payload) -> None:
    client = make_client([])
    created = client.post("/api/profiles", json=profile_payload)
    assert created.status_code == 201
    profile = created.json()
    assert client.get(f"/api/profiles/{profile['id']}").json() == profile
    assert client.get("/api/profiles").json() == [profile]
    assert client.get("/api/profiles/missing").status_code == 404


def test_lesson_topic_defaults_to_main_topic(make_client, profile_payload) -> None:
    client = make_client([])
    user_id = client.post("/api/profiles", json=profile_payload).json()["id"]
    lesson = client.post("/api/lessons", json={"user_id": user_id}).json()
    assert lesson["topic"] == "Job interview preparation"
    assert lesson["status"] == "active"
    assert client.get("/api/lessons", params={"user_id": user_id}).json() == [lesson]


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
