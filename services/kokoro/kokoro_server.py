#!/usr/bin/env python3
"""Kokoro TTS service - fast lightweight TTS.

Runs natively on Windows/Ubuntu (port 8081).
Model: Kokoro-82M (ONNX optimized)
"""

import io
import logging

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from scipy.io import wavfile

try:
    from kokoro_onnx import Kokoro
except ImportError:
    # Fallback for different package structure
    try:
        from kokoro import Kokoro
    except ImportError:
        raise ImportError("kokoro-onnx package not installed. Run: pip install kokoro-onnx")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Kokoro TTS", version="1.0.0")

# Initialize Kokoro model
kokoro_model = None


@app.on_event("startup")
async def load_model():
    global kokoro_model
    from pathlib import Path
    import os
    
    logger.info("Loading Kokoro TTS model...")
    
    # Use user's cache directory for models
    cache_dir = Path.home() / ".cache" / "kokoro"
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    model_path = cache_dir / "kokoro-v0_19.onnx"
    voices_path = cache_dir / "voices.bin"
    
    # Download models if they don't exist
    if not model_path.exists() or not voices_path.exists():
        logger.info("Downloading Kokoro models to %s...", cache_dir)
        import urllib.request
        
        base_url = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/"
        
        if not model_path.exists():
            logger.info("Downloading kokoro-v0_19.onnx...")
            urllib.request.urlretrieve(
                base_url + "kokoro-v0_19.onnx",
                model_path
            )
        
        if not voices_path.exists():
            logger.info("Downloading voices.bin...")
            urllib.request.urlretrieve(
                base_url + "voices.bin",
                voices_path
            )
        
        logger.info("Models downloaded successfully")
    
    kokoro_model = Kokoro(str(model_path), str(voices_path))
    logger.info("Kokoro model loaded successfully")


class TTSRequest(BaseModel):
    """Request body for TTS generation."""
    text: str = Field(..., description="Text to synthesize", max_length=5000)
    voice: str = Field("af_heart", description="Voice ID")
    speed: float = Field(1.0, description="Speech speed multiplier", ge=0.5, le=2.0)


AVAILABLE_VOICES = [
    "af_heart", "af_bella", "af_nicole", "af_sarah", "af_sky",
    "am_adam", "am_michael",
    "bf_emma", "bf_isabella",
    "bm_george", "bm_lewis"
]


@app.post("/v1/tts")
async def text_to_speech(request: TTSRequest):
    """Generate speech from text using Kokoro TTS.
    
    Returns WAV audio (24kHz mono).
    """
    if not kokoro_model:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    if request.voice not in AVAILABLE_VOICES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid voice. Available: {', '.join(AVAILABLE_VOICES)}"
        )
    
    try:
        logger.info(f"Generating TTS: {len(request.text)} chars, voice={request.voice}")
        
        # Generate audio using Kokoro
        samples, sample_rate = kokoro_model.create(
            request.text,
            voice=request.voice,
            speed=request.speed,
        )
        
        # Convert to WAV bytes
        wav_buffer = io.BytesIO()
        wavfile.write(wav_buffer, sample_rate, samples.astype(np.int16))
        wav_bytes = wav_buffer.getvalue()
        
        logger.info(f"Generated {len(wav_bytes)} bytes of audio")
        
        return Response(
            content=wav_bytes,
            media_type="audio/wav",
            headers={
                "Content-Disposition": "attachment; filename=speech.wav"
            }
        )
    except Exception as e:
        logger.error(f"TTS generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"TTS error: {e}")


@app.get("/v1/voices")
async def list_voices():
    """List available voices."""
    return {
        "voices": AVAILABLE_VOICES,
        "default": "af_heart"
    }


@app.get("/v1/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "model": "Kokoro-82M",
        "voices": len(AVAILABLE_VOICES)
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081, log_level="info")
