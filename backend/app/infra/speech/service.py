import asyncio
import logging

from app.config import Settings
from app.infra.speech.groq_stt import GroqTranscriber
from app.infra.speech.stt import WhisperTranscriber
from app.infra.speech.tts import KokoroSynthesizer

logger = logging.getLogger(__name__)


class DefaultSpeechService:
    """Kokoro TTS in this process. STT with local Whisper, or with Groq's hosted Whisper
    (`STT_PROVIDER=groq`), falling back to local Whisper when a Groq request fails.

    Blocking model calls run in threads.
    """

    def __init__(self, settings: Settings, groq: GroqTranscriber | None = None) -> None:
        self._local_stt = WhisperTranscriber(settings.whisper_model, settings.whisper_device)
        self._tts = KokoroSynthesizer(settings.tts_voice)
        self._groq = groq
        if self._groq is None and settings.stt_provider == "groq":
            if settings.groq_api_key:
                self._groq = GroqTranscriber(settings.groq_api_key, settings.groq_stt_model)
            else:
                logger.error("STT_PROVIDER=groq but GROQ_API_KEY is empty; using local Whisper")

    async def transcribe(self, audio: bytes) -> str:
        if self._groq is not None:
            try:
                return await self._groq.transcribe(audio)
            except Exception:
                logger.exception("Groq transcription failed; falling back to local Whisper")
        return await asyncio.to_thread(self._local_stt.transcribe, audio)

    async def synthesize(self, text: str) -> bytes:
        return await asyncio.to_thread(self._tts.synthesize, text)

    async def warm_up(self) -> None:
        """Load the models (downloading them on first run) so the first request is fast.

        With Groq, local Whisper is only a fallback, so it loads on first use instead.
        """
        if self._groq is None:
            await asyncio.to_thread(self._local_stt.load)
        # The first synthesis compiles kernels; do it now rather than on a real reply.
        await self.synthesize("Hello!")
        logger.info("Speech models ready (speech to text: %s)", self.stt_backend)

    @property
    def stt_backend(self) -> str:
        return "groq" if self._groq is not None else "local"

    async def close(self) -> None:
        if self._groq is not None:
            await self._groq.close()
