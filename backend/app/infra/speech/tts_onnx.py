"""Text to speech with the quantized ONNX build of Kokoro-82M (`TTS_ENGINE=onnx`).

An optional, faster engine for CPU servers: about 2.3x the speed of the PyTorch engine and
a third of its memory on the 4-core ARM server. Phonemes and the voice come from the same
Kokoro pipeline; only the neural network that turns them into audio is different.
"""

import hashlib
import json
import logging
import threading
from pathlib import Path

import numpy as np

from app.infra.speech.tts import KOKORO_REPO, to_wav

logger = logging.getLogger(__name__)

ONNX_REPO = "onnx-community/Kokoro-82M-v1.0-ONNX"
# A community conversion, so the exact file is pinned: a later change in that repository
# cannot reach production. Do not switch to `model_q8f16.onnx`: it produces broken audio.
ONNX_REVISION = "1939ad2a8e416c0acfeecc08a694d14ef25f2231"
ONNX_FILE = "onnx/model_quantized.onnx"
ONNX_SHA256 = "fbae9257e1e05ffc727e951ef9b9c98418e6d79f1c9b6b13bd59f5c9028a1478"


def verify_sha256(path: Path, expected: str) -> None:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise ValueError(f"Checksum mismatch for {path.name}")


class OnnxKokoroSynthesizer:
    """Loads the model on first use; `synthesize` is blocking (run it in a thread)."""

    def __init__(self, voice: str) -> None:
        self._voice = voice
        # Kokoro voice names start with the language code: "a" = American, "b" = British.
        self._lang_code = voice[0]
        self._session = None
        self._g2p = None
        self._vocab: dict[str, int] = {}
        self._voice_pack: np.ndarray | None = None
        self._lock = threading.Lock()

    def load(self) -> None:
        with self._lock:
            if self._session is not None:
                return
            import onnxruntime
            from huggingface_hub import hf_hub_download
            from kokoro import KPipeline

            logger.info("Loading quantized ONNX Kokoro (voice %s)", self._voice)
            model_path = hf_hub_download(ONNX_REPO, ONNX_FILE, revision=ONNX_REVISION)
            verify_sha256(Path(model_path), ONNX_SHA256)
            with open(hf_hub_download(KOKORO_REPO, "config.json")) as file:
                self._vocab = json.load(file)["vocab"]
            # model=False: the pipeline only turns text into phonemes.
            self._g2p = KPipeline(lang_code=self._lang_code, repo_id=KOKORO_REPO, model=False)
            self._voice_pack = self._g2p.load_voice(self._voice).numpy()
            options = onnxruntime.SessionOptions()
            options.inter_op_num_threads = 1
            options.execution_mode = onnxruntime.ExecutionMode.ORT_SEQUENTIAL
            # Set last, so a failed load is retried by the next request.
            self._session = onnxruntime.InferenceSession(
                model_path, options, providers=["CPUExecutionProvider"]
            )

    def _infer(self, phonemes: str) -> np.ndarray:
        # 0 pads both ends. The voice has one style vector per phoneme count.
        ids = [0, *(self._vocab[p] for p in phonemes if p in self._vocab), 0]
        output = self._session.run(
            None,
            {
                "input_ids": np.array([ids], dtype=np.int64),
                "style": self._voice_pack[len(phonemes) - 1].astype(np.float32),
                "speed": np.ones(1, dtype=np.float32),
            },
        )[0]
        return np.squeeze(output)

    def synthesize(self, text: str) -> bytes:
        """Return the speech as a 16-bit mono WAV file."""
        self.load()
        with self._lock:
            chunks = [self._infer(result.phonemes) for result in self._g2p(text)]
        return to_wav(chunks)
