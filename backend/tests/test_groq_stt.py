import asyncio

import httpx
import pytest

from app.config import Settings
from app.speech.groq_stt import TRANSCRIPTIONS_URL, GroqTranscriber, upload_filename
from app.speech.service import DefaultSpeechService

WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 16
MP4 = b"\x00\x00\x00\x20ftypM4A " + b"\x00" * 16


def run(coroutine):
    return asyncio.run(coroutine)


def groq_with(handler) -> GroqTranscriber:
    return GroqTranscriber(
        "test-key",
        "whisper-large-v3-turbo",
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


@pytest.mark.parametrize(
    ("audio", "name"),
    [
        (WEBM, "answer.webm"),
        (MP4, "answer.mp4"),
        (b"OggS" + b"\x00" * 8, "answer.ogg"),
        (b"RIFF\x00\x00\x00\x00WAVE", "answer.wav"),
        (b"ID3\x04", "answer.mp3"),
        (b"unknown", "answer.webm"),
    ],
)
def test_upload_filename_matches_the_audio_format(audio: bytes, name: str) -> None:
    assert upload_filename(audio) == name


def test_groq_request_and_response() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["Authorization"]
        seen["body"] = request.content
        return httpx.Response(200, json={"text": " I am work as developer. "})

    groq = groq_with(handler)
    assert run(groq.transcribe(MP4)) == "I am work as developer."
    assert seen["url"] == TRANSCRIPTIONS_URL
    assert seen["auth"] == "Bearer test-key"
    body = seen["body"]
    assert b'name="model"\r\n\r\nwhisper-large-v3-turbo' in body
    assert b'name="language"\r\n\r\nen' in body
    assert b'name="temperature"\r\n\r\n0' in body
    assert b'filename="answer.mp4"' in body
    # No prompt: it made Whisper "fix" the learner's grammar.
    assert b'name="prompt"' not in body


class FakeLocalWhisper:
    def __init__(self) -> None:
        self.calls = 0

    def transcribe(self, audio: bytes) -> str:
        self.calls += 1
        return "local transcript"

    def load(self) -> None:
        pass


def service_with(handler) -> tuple[DefaultSpeechService, FakeLocalWhisper]:
    settings = Settings(stt_provider="groq", groq_api_key="test-key")
    service = DefaultSpeechService(settings, groq=groq_with(handler))
    local = FakeLocalWhisper()
    service._local_stt = local
    return service, local


def test_service_uses_groq_when_configured() -> None:
    service, local = service_with(lambda request: httpx.Response(200, json={"text": "groq"}))
    assert service.stt_backend == "groq"
    assert run(service.transcribe(WEBM)) == "groq"
    assert local.calls == 0


def test_service_falls_back_to_local_whisper_when_groq_fails() -> None:
    service, local = service_with(lambda request: httpx.Response(429, json={"error": "limit"}))
    assert run(service.transcribe(WEBM)) == "local transcript"
    assert local.calls == 1


def test_groq_without_key_uses_local_whisper() -> None:
    service = DefaultSpeechService(Settings(stt_provider="groq", groq_api_key=""))
    assert service.stt_backend == "local"


def test_local_provider_by_default() -> None:
    assert DefaultSpeechService(Settings()).stt_backend == "local"
