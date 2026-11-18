import logging

from fastapi import APIRouter, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field

from app.api.deps import SpeechDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/speech", tags=["speech"])

# ~10 minutes of compressed browser audio; far more than one spoken answer.
MAX_AUDIO_BYTES = 10 * 1024 * 1024


class TranscriptionResponse(BaseModel):
    text: str


class SynthesisRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


@router.post("/transcribe")
async def transcribe(audio: UploadFile, speech: SpeechDep) -> TranscriptionResponse:
    """Transcribe a recorded answer (any format ffmpeg can decode, e.g. webm/opus)."""
    data = await audio.read(MAX_AUDIO_BYTES + 1)
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Recording is too long")
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Recording is empty")
    try:
        text = await speech.transcribe(data)
    except Exception as error:
        logger.exception("Transcription failed")
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "Could not transcribe the recording"
        ) from error
    return TranscriptionResponse(text=text)


@router.post(
    "/synthesize",
    response_class=Response,
    responses={200: {"content": {"audio/wav": {}}}},
)
async def synthesize(body: SynthesisRequest, speech: SpeechDep) -> Response:
    """Read text aloud with the tutor's voice; returns a WAV file."""
    try:
        audio = await speech.synthesize(body.text)
    except Exception as error:
        logger.exception("Speech synthesis failed")
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "Could not generate speech"
        ) from error
    return Response(content=audio, media_type="audio/wav")
