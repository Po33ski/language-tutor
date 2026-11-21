import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage
from pydantic import Field

from app.config import Settings
from app.domain.lessons.models import LessonSummary
from app.domain.moderation.policy import ALLOWED, ModerationCategory, ModerationVerdict
from app.main import create_app


class FakeTutorModel(GenericFakeChatModel):
    """Replays scripted AI messages; tool binding is a no-op. `inputs` records the
    messages of every call, as the model received them."""

    disable_streaming: bool = True
    inputs: list[list[BaseMessage]] = Field(default_factory=list)

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.inputs.append(list(messages))
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


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


class FakeModerator:
    """Blocks messages that contain "BLOCK-ME" (as an insult); records every check."""

    def __init__(self) -> None:
        self.checked: list[str] = []

    async def check(self, text: str) -> ModerationVerdict:
        self.checked.append(text)
        if "BLOCK-ME" in text:
            return ModerationVerdict(
                allowed=False, category=ModerationCategory.INSULT, scores={"insult": 0.99}
            )
        return ALLOWED

    async def warm_up(self) -> None:
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
def moderator() -> FakeModerator:
    return FakeModerator()


STRONG_PASSWORD = "correct horse battery staple"


def sign_up(client: TestClient, email: str = "anna@example.com") -> dict:
    """Create an account and send its session token with every later request."""
    response = client.post("/api/auth/signup", json={"email": email, "password": STRONG_PASSWORD})
    assert response.status_code == 201, response.text
    body = response.json()
    client.headers["Authorization"] = f"Bearer {body['token']}"
    return body


@pytest.fixture
def make_client(tmp_path, summarizer, speech, moderator) -> Iterator:
    """Factory: a test client whose tutor replays the given AI messages, signed in to a
    fresh account unless `signed_in=False`. The breached-password check (a network call)
    is off unless a test turns it on."""
    clients = []

    def factory(
        responses: list[AIMessage], *, signed_in: bool = True, **settings_overrides
    ) -> TestClient:
        settings_overrides.setdefault("password_breach_check", False)
        settings = Settings(data_dir=tmp_path, anthropic_api_key="test", **settings_overrides)
        model = FakeTutorModel(messages=iter(responses))
        client = TestClient(create_app(settings, model, summarizer, speech, moderator))
        client.model = model  # lets tests inspect what the tutor model received
        client.__enter__()  # run the lifespan (opens SQLite, builds the agent)
        clients.append(client)
        if signed_in:
            sign_up(client)
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
