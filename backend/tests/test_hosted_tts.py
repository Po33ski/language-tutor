import asyncio
import json
import sqlite3
from datetime import date

import httpx
import pytest

from app.config import Settings
from app.infra.persistence.users import UserStore
from app.infra.speech.deepinfra_tts import SPEECH_URL, DeepInfraSynthesizer
from app.infra.speech.service import DefaultSpeechService
from tests.conftest import sign_up

WAV = b"RIFF\x00\x00\x00\x00WAVEfmt "
DAY = date(2026, 11, 21)


class FakeLocalKokoro:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def synthesize(self, text: str) -> bytes:
        self.calls.append(text)
        return b"local"


def deepinfra(handler) -> DeepInfraSynthesizer:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return DeepInfraSynthesizer("test-key", "hexgrad/Kokoro-82M", "af_heart", client)


def service_with(handler) -> tuple[DefaultSpeechService, FakeLocalKokoro]:
    settings = Settings(_env_file=None, tts_engine="deepinfra")
    service = DefaultSpeechService(settings, hosted_tts=deepinfra(handler))
    local = FakeLocalKokoro()
    service._tts = local
    return service, local


def speak(service: DefaultSpeechService, **kwargs) -> bytes:
    async def scenario() -> bytes:
        try:
            return await service.synthesize("Hello there", **kwargs)
        finally:
            await service.close()

    return asyncio.run(scenario())


def test_request_matches_the_deepinfra_api() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(url=str(request.url), auth=request.headers["Authorization"])
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, content=WAV)

    assert asyncio.run(deepinfra(handler).synthesize("Hello")) == WAV
    assert seen["url"] == SPEECH_URL
    assert seen["auth"] == "Bearer test-key"
    assert seen["body"] == {
        "model": "hexgrad/Kokoro-82M",
        "input": "Hello",
        "voice": "af_heart",
        "response_format": "wav",
    }


def test_a_non_wav_answer_is_an_error() -> None:
    engine = deepinfra(lambda request: httpx.Response(200, content=b"not audio"))
    with pytest.raises(ValueError, match="WAV"):
        asyncio.run(engine.synthesize("Hello"))


def test_local_model_stays_the_default() -> None:
    settings = Settings(_env_file=None)
    assert settings.tts_engine == "torch"
    assert DefaultSpeechService(settings).hosted_tts_enabled is False


def test_missing_key_uses_the_local_model() -> None:
    settings = Settings(_env_file=None, tts_engine="deepinfra", deepinfra_api_key="")
    assert DefaultSpeechService(settings).hosted_tts_enabled is False


def test_hosted_engine_needs_explicit_permission() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, content=WAV)

    service, local = service_with(handler)
    assert speak(service) == b"local"  # not allowed by default, so nothing is billed
    assert calls == []
    assert local.calls == ["Hello there"]


def test_hosted_engine_is_used_when_allowed() -> None:
    service, local = service_with(lambda request: httpx.Response(200, content=WAV))
    assert speak(service, allow_hosted=True) == WAV
    assert local.calls == []


@pytest.mark.parametrize("status", [401, 402, 429, 500])
def test_hosted_failure_falls_back_to_local(status: int) -> None:
    service, local = service_with(lambda request: httpx.Response(status))
    assert speak(service, allow_hosted=True) == b"local"
    assert local.calls == ["Hello there"]


def test_warm_up_never_calls_the_paid_api() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, content=WAV)

    service, local = service_with(handler)

    service._groq = object()  # keep the real Whisper from loading
    asyncio.run(service.warm_up())
    assert calls == []
    assert local.calls == []


def test_consume_counts_amounts_without_overshooting(tmp_path) -> None:
    async def scenario() -> list[bool]:
        async with UserStore.open(tmp_path / "users.db") as users:
            return [
                await users.consume(DAY, "u", "chars", 10, amount=6),
                await users.consume(DAY, "u", "chars", 10, amount=5),  # 11 would not fit
                await users.consume(DAY, "u", "chars", 10, amount=4),  # exactly 10 fits
                await users.consume(DAY, "u", "chars", 10, amount=1),
                await users.consume(DAY, "other", "chars", 10, amount=11),  # never fits
            ]

    assert asyncio.run(scenario()) == [True, False, True, False, False]


def _say(client, text: str) -> int:
    return client.post("/api/speech/synthesize", json={"text": text}).status_code


def test_budget_per_account_switches_to_local(make_client, speech) -> None:
    speech.hosted_tts_enabled = True
    client = make_client([], user_daily_hosted_tts_chars=10)
    assert _say(client, "12345678") == 200
    assert _say(client, "123") == 200  # over the limit: still answered, locally
    assert speech.hosted_flags == [True, False]

    sign_up(client, email="bob@example.com")  # another account has its own budget
    assert _say(client, "12345678") == 200
    assert speech.hosted_flags[-1] is True


def test_budget_for_the_whole_app(make_client, speech) -> None:
    speech.hosted_tts_enabled = True
    client = make_client([], daily_hosted_tts_chars_total=10)
    assert _say(client, "12345678") == 200
    sign_up(client, email="bob@example.com")
    assert _say(client, "12345678") == 200
    assert speech.hosted_flags == [True, False]


def test_local_engine_uses_no_budget(make_client, speech, tmp_path) -> None:
    client = make_client([], user_daily_hosted_tts_chars=1)
    assert _say(client, "A much longer sentence") == 200
    assert speech.hosted_flags == [False]
    rows = sqlite3.connect(tmp_path / "users.db").execute(
        "SELECT COUNT(*) FROM daily_usage WHERE kind = 'hosted_tts_chars'"
    )
    assert rows.fetchone() == (0,)
