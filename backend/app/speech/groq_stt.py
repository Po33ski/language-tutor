"""Speech to text with Whisper hosted by Groq (OpenAI-compatible API).

Much faster than Whisper on a small CPU server, and it is the same model
(`whisper-large-v3-turbo`) that runs locally on the GPU.
"""

import httpx

TRANSCRIPTIONS_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


def upload_filename(audio: bytes) -> str:
    """Name the upload after its real format: Groq detects the format from the extension."""
    if audio[:4] == b"\x1a\x45\xdf\xa3":  # EBML header: WebM (Chrome, Firefox, Android)
        return "answer.webm"
    if audio[4:8] == b"ftyp":  # MP4 container (Safari, iOS)
        return "answer.mp4"
    if audio[:4] == b"OggS":
        return "answer.ogg"
    if audio[:4] == b"RIFF" and audio[8:12] == b"WAVE":
        return "answer.wav"
    if audio[:4] == b"fLaC":
        return "answer.flac"
    if audio[:3] == b"ID3" or audio[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "answer.mp3"
    return "answer.webm"


class GroqTranscriber:
    """Async client for Groq's transcription endpoint. Reuses one HTTP connection."""

    def __init__(
        self,
        api_key: str,
        model: str,
        client: httpx.AsyncClient | None = None,
        timeout: float = 30,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._client = client or httpx.AsyncClient(timeout=timeout)

    async def transcribe(self, audio: bytes) -> str:
        response = await self._client.post(
            TRANSCRIPTIONS_URL,
            headers={"Authorization": f"Bearer {self._api_key}"},
            # Same settings as local Whisper: English, deterministic, and no prompt,
            # because a prompt made Whisper fix the learner's grammar.
            data={
                "model": self._model,
                "language": "en",
                "temperature": "0",
                "response_format": "json",
            },
            files={"file": (upload_filename(audio), audio)},
        )
        response.raise_for_status()
        return response.json()["text"].strip()

    async def close(self) -> None:
        await self._client.aclose()
