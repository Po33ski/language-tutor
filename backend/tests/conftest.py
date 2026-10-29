import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from app.config import Settings
from app.main import create_app


class FakeTutorModel(GenericFakeChatModel):
    """Replays scripted AI messages; tool binding is a no-op."""

    disable_streaming: bool = True

    def bind_tools(self, tools, **kwargs):
        return self


def mistake_call(original: str, corrected: str, explanation: str) -> AIMessage:
    args = {"original": original, "corrected": corrected, "explanation": explanation}
    return AIMessage(
        content="", tool_calls=[{"name": "record_mistake", "args": args, "id": "call-1"}]
    )


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


@pytest.fixture
def make_client(tmp_path) -> Iterator:
    """Factory: a test client whose tutor replays the given AI messages."""
    clients = []

    def factory(responses: list[AIMessage]) -> TestClient:
        settings = Settings(data_dir=tmp_path, anthropic_api_key="test")
        model = FakeTutorModel(messages=iter(responses))
        client = TestClient(create_app(settings, model))
        client.__enter__()  # run the lifespan (opens SQLite, builds the agent)
        clients.append(client)
        return client

    yield factory
    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture
def profile_payload() -> dict:
    return {
        "name": "Anna",
        "level": "B1",
        "main_topic": "Job interview preparation",
        "goal": "Get a developer job in London",
    }
