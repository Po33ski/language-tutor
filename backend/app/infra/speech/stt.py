"""Speech to text with Whisper (faster-whisper), run locally."""

import io
import logging
import threading

from app.infra.speech.cuda import preload_cuda12_libraries

logger = logging.getLogger(__name__)


class WhisperTranscriber:
    """Loads the model on first use; `transcribe` is blocking (run it in a thread)."""

    def __init__(self, model_name: str, device: str = "auto") -> None:
        self._model_name = model_name
        self._device = device
        self._model = None
        self._lock = threading.Lock()

    def load(self) -> None:
        with self._lock:
            if self._model is not None:
                return
            preload_cuda12_libraries()
            import ctranslate2
            from faster_whisper import WhisperModel

            device = self._device
            if device == "auto":
                device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
            compute_type = "float16" if device == "cuda" else "int8"
            logger.info("Loading Whisper %s on %s", self._model_name, device)
            self._model = WhisperModel(self._model_name, device=device, compute_type=compute_type)

    def transcribe(self, audio: bytes) -> str:
        self.load()
        with self._lock:
            segments, _ = self._model.transcribe(
                io.BytesIO(audio),
                language="en",
                beam_size=5,
                vad_filter=True,
                condition_on_previous_text=False,
                # No initial_prompt: it made Whisper "fix" learner grammar in testing,
                # and the tutor needs to see the learner's real mistakes.
            )
            return " ".join(segment.text.strip() for segment in segments).strip()
