import hashlib
import io
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf
from pydantic import ValidationError

from app.config import Settings
from app.infra.speech.service import DefaultSpeechService
from app.infra.speech.tts import SAMPLE_RATE, KokoroSynthesizer
from app.infra.speech.tts_onnx import OnnxKokoroSynthesizer, verify_sha256


class FakeSession:
    def __init__(self) -> None:
        self.inputs: list[dict] = []

    def run(self, outputs, inputs: dict) -> list[np.ndarray]:
        self.inputs.append(inputs)
        return [np.full((1, 2400), 0.25, dtype=np.float32)]


def loaded_onnx_engine(phonemes: list[str]) -> tuple[OnnxKokoroSynthesizer, FakeSession]:
    """An engine with fakes in place of the real model, phonemizer and voice."""
    engine = OnnxKokoroSynthesizer("af_heart")
    session = FakeSession()
    engine._session = session
    engine._vocab = {"a": 7, "b": 9}
    engine._voice_pack = np.arange(510 * 256, dtype=np.float64).reshape(510, 1, 256)
    engine._g2p = lambda text: [SimpleNamespace(phonemes=p) for p in phonemes]
    return engine, session


def test_full_pytorch_model_is_the_default() -> None:
    settings = Settings(_env_file=None)
    assert settings.tts_engine == "torch"
    assert isinstance(DefaultSpeechService(settings)._tts, KokoroSynthesizer)


def test_quantized_engine_is_opt_in() -> None:
    service = DefaultSpeechService(Settings(_env_file=None, tts_engine="onnx"))
    assert isinstance(service._tts, OnnxKokoroSynthesizer)


def test_unknown_engine_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, tts_engine="other")


def test_onnx_inputs_match_kokoro() -> None:
    engine, session = loaded_onnx_engine(["ab?"])
    engine.synthesize("Hi")
    inputs = session.inputs[0]
    assert inputs["input_ids"].tolist() == [[0, 7, 9, 0]]  # padded; unknown phoneme dropped
    # The style vector is chosen by the phoneme count, including the unknown one.
    assert inputs["style"].shape == (1, 256)
    assert inputs["style"][0, 0] == 2 * 256
    assert inputs["style"].dtype == np.float32
    assert inputs["speed"].tolist() == [1.0]


def test_onnx_engine_joins_chunks_into_one_wav() -> None:
    engine, _ = loaded_onnx_engine(["ab", "ba"])
    audio, rate = sf.read(io.BytesIO(engine.synthesize("Two chunks")))
    assert rate == SAMPLE_RATE
    assert len(audio) == 4800


def test_onnx_engine_handles_text_without_speech() -> None:
    engine, session = loaded_onnx_engine([])
    audio, _ = sf.read(io.BytesIO(engine.synthesize("...")))
    assert len(audio) == 0
    assert session.inputs == []


def test_model_checksum_is_verified(tmp_path) -> None:
    model = tmp_path / "model.onnx"
    model.write_bytes(b"model")
    verify_sha256(model, hashlib.sha256(b"model").hexdigest())
    with pytest.raises(ValueError, match="Checksum mismatch"):
        verify_sha256(model, hashlib.sha256(b"tampered").hexdigest())
