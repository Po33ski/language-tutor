import asyncio
import threading

import pytest

from app.config import Settings
from app.infra.speech.service import DefaultSpeechService


class GatedSynthesizer:
    """Holds every synthesis until `release` is set, and records what ran and where."""

    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.order: list[str] = []
        self.threads: set[str] = set()

    def synthesize(self, text: str) -> bytes:
        self.started.set()
        assert self.release.wait(timeout=5)
        self.order.append(text)
        self.threads.add(threading.current_thread().name)
        if text == "fails":
            raise RuntimeError("model error")
        return text.encode()


@pytest.fixture
def queued() -> tuple[DefaultSpeechService, GatedSynthesizer]:
    service = DefaultSpeechService(Settings(stt_provider="local"))
    synthesizer = GatedSynthesizer()
    service._tts = synthesizer
    return service, synthesizer


def test_sentences_run_first_in_first_out_on_one_thread(queued) -> None:
    service, synthesizer = queued
    texts = [f"sentence {index}" for index in range(12)]

    async def scenario() -> list[bytes]:
        tasks = [asyncio.create_task(service.synthesize(text)) for text in texts]
        await asyncio.to_thread(synthesizer.started.wait, 2)
        synthesizer.release.set()
        results = await asyncio.gather(*tasks)
        await service.close()
        return results

    results = asyncio.run(scenario())
    assert synthesizer.order == texts
    assert results == [text.encode() for text in texts]  # each caller gets its own audio
    assert len(synthesizer.threads) == 1
    assert next(iter(synthesizer.threads)).startswith("tts")


def test_waiting_sentences_leave_the_shared_thread_pool_free(queued) -> None:
    service, synthesizer = queued

    async def scenario() -> str:
        # More than the shared pool has threads on any machine this runs on.
        tasks = [asyncio.create_task(service.synthesize("wait")) for _ in range(64)]
        await asyncio.to_thread(synthesizer.started.wait, 2)
        # Moderation and password hashing run like this while speech is queued.
        result = await asyncio.wait_for(asyncio.to_thread(lambda: "not blocked"), timeout=2)
        synthesizer.release.set()
        await asyncio.gather(*tasks)
        await service.close()
        return result

    assert asyncio.run(scenario()) == "not blocked"


def test_a_failed_sentence_does_not_stop_the_queue(queued) -> None:
    service, synthesizer = queued
    synthesizer.release.set()

    async def scenario() -> list:
        results = await asyncio.gather(
            service.synthesize("fails"), service.synthesize("next"), return_exceptions=True
        )
        await service.close()
        return results

    failed, following = asyncio.run(scenario())
    assert isinstance(failed, RuntimeError)
    assert following == b"next"
