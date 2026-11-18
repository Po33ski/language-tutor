import asyncio
import logging
from typing import Protocol

from app.config import Settings
from app.speech.stt import WhisperTranscriber
from app.speech.tts import KokoroSynthesizer

logger = logging.getLogger(__name__)


class SpeechService(Protocol):
    async def transcribe(self, audio: bytes) -> str: ...

    async def synthesize(self, text: str) -> bytes: ...

    async def warm_up(self) -> None: ...


class LocalSpeechService:
    """Whisper + Kokoro running in this process. Blocking model calls run in threads."""

    def __init__(self, settings: Settings) -> None:
        self._stt = WhisperTranscriber(settings.whisper_model, settings.whisper_device)
        self._tts = KokoroSynthesizer(settings.tts_voice)

    async def transcribe(self, audio: bytes) -> str:
        return await asyncio.to_thread(self._stt.transcribe, audio)

    async def synthesize(self, text: str) -> bytes:
        return await asyncio.to_thread(self._tts.synthesize, text)

    async def warm_up(self) -> None:
        """Load both models (downloading them on first run) so the first request is fast."""
        await asyncio.to_thread(self._stt.load)
        # The first synthesis compiles GPU kernels; do it now rather than on a real reply.
        await self.synthesize("Hello!")
        logger.info("Speech models ready")
