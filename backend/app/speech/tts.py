"""Text to speech with Kokoro-82M, run locally."""

import io
import logging
import threading

import numpy as np
import soundfile as sf

logger = logging.getLogger(__name__)

SAMPLE_RATE = 24_000
KOKORO_REPO = "hexgrad/Kokoro-82M"


class KokoroSynthesizer:
    """Loads the model on first use; `synthesize` is blocking (run it in a thread)."""

    def __init__(self, voice: str) -> None:
        self._voice = voice
        # Kokoro voice names start with the language code: "a" = American, "b" = British.
        self._lang_code = voice[0]
        self._pipeline = None
        self._lock = threading.Lock()

    def load(self) -> None:
        with self._lock:
            if self._pipeline is not None:
                return
            from kokoro import KPipeline

            logger.info("Loading Kokoro (voice %s)", self._voice)
            self._pipeline = KPipeline(lang_code=self._lang_code, repo_id=KOKORO_REPO)

    def synthesize(self, text: str) -> bytes:
        """Return the speech as a 16-bit mono WAV file."""
        self.load()
        with self._lock:
            chunks = [result.audio.numpy() for result in self._pipeline(text, voice=self._voice)]
        audio = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
        buffer = io.BytesIO()
        sf.write(buffer, audio, SAMPLE_RATE, format="WAV", subtype="PCM_16")
        return buffer.getvalue()
