"""Text to speech with Kokoro-82M hosted by DeepInfra (`TTS_ENGINE=deepinfra`).

An optional, paid engine (billed per character; DeepInfra requires a card or a prepaid
balance). It takes synthesis off the server's CPU. The local Kokoro stays the fallback.
"""

import httpx

SPEECH_URL = "https://api.deepinfra.com/v1/openai/audio/speech"


class DeepInfraSynthesizer:
    """Async client for DeepInfra's OpenAI-compatible speech endpoint."""

    def __init__(
        self,
        api_key: str,
        model: str,
        voice: str,
        client: httpx.AsyncClient | None = None,
        timeout: float = 20,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._voice = voice
        self._client = client or httpx.AsyncClient(timeout=timeout)

    async def synthesize(self, text: str) -> bytes:
        """Return the speech as a WAV file."""
        response = await self._client.post(
            SPEECH_URL,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "model": self._model,
                "input": text,
                "voice": self._voice,
                "response_format": "wav",
            },
        )
        response.raise_for_status()
        audio = response.content
        if audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
            raise ValueError("DeepInfra did not return a WAV file")
        return audio

    async def close(self) -> None:
        await self._client.aclose()
