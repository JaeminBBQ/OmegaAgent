"""Speech proxy routes — STT and TTS via desktop GPU services."""

import logging

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/speech", tags=["speech"])


class TTSRequest(BaseModel):
    """Request body for text-to-speech."""

    text: str = Field(..., description="Text to synthesize")
    provider: str = Field("kokoro", description="TTS provider: kokoro (fast) or fish (quality)")
    voice: str = Field("af_heart", description="Voice ID (Kokoro only)")
    format: str = Field("wav", description="Output format: wav or mp3")


@router.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    """Transcribe uploaded audio via Whisper on the desktop GPU.

    Send a WAV/MP3 file, get back transcribed text.
    """
    from main import speech

    try:
        audio_bytes = await file.read()
        text = await speech.transcribe(
            audio_bytes=audio_bytes,
            filename=file.filename or "audio.wav",
        )
        return {"text": text}
    except Exception as exc:
        logger.error("STT failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail=f"STT service error: {exc}")


@router.post("/tts")
async def text_to_speech(request: TTSRequest):
    """Generate speech audio from text via desktop GPU TTS.

    Returns raw audio bytes (WAV by default).
    """
    from core.speech import TTSProvider
    from main import speech

    provider = TTSProvider.KOKORO if request.provider == "kokoro" else TTSProvider.FISH

    try:
        audio_bytes = await speech.speak(
            text=request.text,
            provider=provider,
            voice=request.voice,
            format=request.format,
        )
        media_type = "audio/wav" if request.format == "wav" else "audio/mpeg"
        return Response(content=audio_bytes, media_type=media_type)
    except Exception as exc:
        logger.error("TTS failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail=f"TTS service error: {exc}")
