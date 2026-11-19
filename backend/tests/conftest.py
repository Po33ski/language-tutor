import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from app.config import Settings
from app.main import create_app
from app.storage.memory import LessonSummary


class FakeTutorModel(GenericFakeChatModel):
    """Replays scripted AI messages; tool binding is a no-op."""

    disable_streaming: bool = True

    def bind_tools(self, tools, **kwargs):
        return self


class FakeSummarizer:
    """Records what it was asked to summarize and returns a fixed summary."""

    def __init__(self) -> None:
        self.summarize_calls: list[dict] = []
        self.progress_calls: list[dict] = []
        self.fail = False

    async def summarize(self, **kwargs) -> LessonSummary:
        if self.fail:
            raise RuntimeError("model unavailable")
        self.summarize_calls.append(kwargs)
        return LessonSummary(
            summary="You introduced yourself.",
            practiced=["self-introduction"],
            recurring_mistakes=["present simple"],
            vocabulary=["background"],
            next_steps=["talk about projects"],
        )

    async def update_progress(self, **kwargs) -> str:
        self.progress_calls.append(kwargs)
        return f"Progress after {len(self.progress_calls)} lesson(s)."


class FakeSpeech:
    """Echo-style speech service: no models, deterministic output."""

    def __init__(self) -> None:
        self.transcript = "I am work as developer"
        self.fail = False

    async def transcribe(self, audio: bytes) -> str:
        if self.fail:
            raise RuntimeError("model unavailable")
        return self.transcript

    async def synthesize(self, text: str) -> bytes:
        if self.fail:
            raise RuntimeError("model unavailable")
        return b"RIFF" + text.encode()

    async def warm_up(self) -> None:
        pass

    async def close(self) -> None:
        pass


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
def summarizer() -> FakeSummarizer:
    return FakeSummarizer()


@pytest.fixture
def speech() -> FakeSpeech:
    return FakeSpeech()


@pytest.fixture
def make_client(tmp_path, summarizer, speech) -> Iterator:
    """Factory: a test client whose tutor replays the given AI messages."""
    clients = []

    def factory(responses: list[AIMessage], **settings_overrides) -> TestClient:
        settings = Settings(data_dir=tmp_path, anthropic_api_key="test", **settings_overrides)
        model = FakeTutorModel(messages=iter(responses))
        client = TestClient(create_app(settings, model, summarizer, speech))
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
