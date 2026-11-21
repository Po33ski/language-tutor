from langchain_core.messages import AIMessage

from app.domain.moderation.policy import (
    BLOCKED_MESSAGES,
    ModerationCategory,
    decide,
    is_addressed,
    strip_quoted,
)
from tests.conftest import parse_sse


def test_quoted_words_are_mentioned_not_used() -> None:
    assert "idiot" not in strip_quoted("How do you say 'idiot' politely?")
    assert "damn" not in strip_quoted('What does "damn" mean?')
    assert "damn" not in strip_quoted("What does “damn” mean?")
    # Apostrophes are not quotes.
    text = "I'm sure you don't know what I'll do."
    assert strip_quoted(text) == text


def test_addressed_messages() -> None:
    for text in ["You are a stupid bot.", "Shut up, you idiot.", "you moron", "Are you dumb?"]:
        assert is_addressed(text), text
    for text in ["This exercise is stupid.", "Do you think this exercise is stupid?"]:
        assert not is_addressed(text), text


def test_policy_blocks_serious_content_and_lets_frustration_through() -> None:
    def category(text: str, **scores: float) -> ModerationCategory | None:
        return decide(text, scores).category

    assert category("I will hurt you.", threat=0.72) is ModerationCategory.THREAT
    assert category("I could kill for a coffee.", threat=0.67) is None
    assert category("...", identity_attack=0.6) is ModerationCategory.HATE
    assert category("...", sexual_explicit=0.21) is ModerationCategory.SEXUAL
    assert category("You are a stupid bot.", insult=1.0) is ModerationCategory.INSULT
    assert category("This exercise is stupid.", insult=1.0) is None
    assert category("This is so damn hard.", toxicity=0.99, obscene=0.99) is None


def test_blocked_message_never_reaches_the_tutor(make_client, profile_payload, moderator) -> None:
    client = make_client([AIMessage("Hi Anna! How are you?"), AIMessage("Glad to hear it!")])
    client.post("/api/profile", json=profile_payload)
    lesson_id = client.post("/api/lessons", json={}).json()["id"]
    client.post(f"/api/lessons/{lesson_id}/messages", json={"content": None})
    calls_before = len(client.model.inputs)

    response = client.post(
        f"/api/lessons/{lesson_id}/messages", json={"content": "BLOCK-ME you idiot"}
    )
    blocked = {"message": BLOCKED_MESSAGES[ModerationCategory.INSULT], "category": "insult"}
    assert parse_sse(response.text) == [("blocked", blocked), ("done", {})]
    assert len(client.model.inputs) == calls_before  # the tutor model was not called
    detail = client.get(f"/api/lessons/{lesson_id}").json()
    assert [m["role"] for m in detail["messages"]] == ["assistant"]  # nothing was stored

    # The kickoff is not checked; learner messages are.
    response = client.post(f"/api/lessons/{lesson_id}/messages", json={"content": "I'm fine"})
    assert ("token", {"text": "Glad to hear it!"}) in parse_sse(response.text)
    assert moderator.checked == ["BLOCK-ME you idiot", "I'm fine"]
