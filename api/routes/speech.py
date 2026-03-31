"""Speech proxy routes — STT and TTS via desktop GPU services."""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from core.config import KOKORO_TTS_URL

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/speech", tags=["speech"])

# Directory for custom voice reference audio
VOICE_DIR = Path("/app/voices") if Path("/app").exists() else Path("./voices")
VOICE_DIR.mkdir(parents=True, exist_ok=True)

# Built-in Kokoro voices
KOKORO_VOICES = [
    {"id": "af_heart", "name": "Heart", "gender": "female", "accent": "american"},
    {"id": "af_bella", "name": "Bella", "gender": "female", "accent": "american"},
    {"id": "af_nicole", "name": "Nicole", "gender": "female", "accent": "american"},
    {"id": "af_sarah", "name": "Sarah", "gender": "female", "accent": "american"},
    {"id": "af_sky", "name": "Sky", "gender": "female", "accent": "american"},
    {"id": "am_adam", "name": "Adam", "gender": "male", "accent": "american"},
    {"id": "am_michael", "name": "Michael", "gender": "male", "accent": "american"},
    {"id": "bf_emma", "name": "Emma", "gender": "female", "accent": "british"},
    {"id": "bf_isabella", "name": "Isabella", "gender": "female", "accent": "british"},
    {"id": "bm_george", "name": "George", "gender": "male", "accent": "british"},
    {"id": "bm_lewis", "name": "Lewis", "gender": "male", "accent": "british"},
]


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

    Voice IDs:
        - Kokoro built-in: af_heart, am_adam, etc.
        - Fish clone: fish:my_voice (loads reference audio from /voices/)

    Returns raw audio bytes (WAV by default).
    """
    from core.speech import TTSProvider
    from main import speech

    voice = request.voice
    reference_audio = None

    # Detect fish:voice_name → use Fish Speech with cloned voice
    if voice.startswith("fish:"):
        provider = TTSProvider.FISH
        voice_name = voice[5:]  # strip "fish:" prefix
        # Look for reference audio file
        for ext in (".wav", ".mp3"):
            ref_path = VOICE_DIR / f"{voice_name}{ext}"
            if ref_path.exists():
                reference_audio = ref_path.read_bytes()
                logger.info("Using cloned voice: %s (%d bytes ref)", voice_name, len(reference_audio))
                break
        if reference_audio is None:
            raise HTTPException(status_code=404, detail=f"Voice reference not found: {voice_name}")
    else:
        provider = TTSProvider.KOKORO if request.provider == "kokoro" else TTSProvider.FISH

    try:
        audio_bytes = await speech.speak(
            text=request.text,
            provider=provider,
            voice=voice,
            format=request.format,
            reference_audio=reference_audio,
        )
        media_type = "audio/wav" if request.format == "wav" else "audio/mpeg"
        return Response(content=audio_bytes, media_type=media_type)
    except Exception as exc:
        logger.error("TTS failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail=f"TTS service error: {exc}")


# --- Voice Management -------------------------------------------------------

@router.get("/voices")
async def list_voices():
    """List all available TTS voices (built-in Kokoro + custom Fish clones)."""
    custom = []
    for f in sorted(VOICE_DIR.glob("*.wav")) + sorted(VOICE_DIR.glob("*.mp3")):
        custom.append({
            "id": f"fish:{f.stem}",
            "name": f.stem.replace("_", " ").title(),
            "type": "custom_clone",
            "file": f.name,
        })

    return {
        "kokoro": KOKORO_VOICES,
        "custom": custom,
    }


@router.get("/voices/manage", response_class=HTMLResponse)
async def voice_manager_page():
    """Simple web UI for managing TTS voices."""
    import httpx

    # Check Kokoro connectivity
    kokoro_status = "unknown"
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.get(f"{KOKORO_TTS_URL}/v1/health")
            kokoro_status = "online" if r.status_code == 200 else "offline"
    except Exception:
        kokoro_status = "offline"

    # List custom voices
    custom_voices = []
    for f in sorted(VOICE_DIR.glob("*.wav")) + sorted(VOICE_DIR.glob("*.mp3")):
        size_kb = f.stat().st_size / 1024
        custom_voices.append({"name": f.stem, "file": f.name, "size_kb": round(size_kb, 1)})

    kokoro_rows = "".join(
        f'<tr><td><code>{v["id"]}</code></td><td>{v["name"]}</td><td>{v["gender"]}</td><td>{v["accent"]}</td></tr>'
        for v in KOKORO_VOICES
    )
    custom_rows = "".join(
        f'<tr><td><code>fish:{v["name"]}</code></td><td>{v["name"].replace("_", " ").title()}</td>'
        f'<td>{v["file"]}</td><td>{v["size_kb"]} KB</td></tr>'
        for v in custom_voices
    ) or '<tr><td colspan="4">No custom voices yet</td></tr>'

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>OmegaAgent — Voice Manager</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{ font-family: -apple-system, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; background: #0d1117; color: #c9d1d9; }}
            h1, h2 {{ color: #58a6ff; }}
            table {{ width: 100%; border-collapse: collapse; margin: 16px 0; }}
            th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #21262d; }}
            th {{ color: #8b949e; font-weight: 600; }}
            code {{ background: #161b22; padding: 2px 6px; border-radius: 4px; color: #79c0ff; }}
            .status {{ display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 0.85em; }}
            .online {{ background: #1b4332; color: #4ade80; }}
            .offline {{ background: #3b1f1f; color: #f87171; }}
            form {{ background: #161b22; padding: 20px; border-radius: 8px; margin: 16px 0; }}
            input[type=file], input[type=text] {{ margin: 8px 0; padding: 8px; background: #0d1117; border: 1px solid #30363d; color: #c9d1d9; border-radius: 4px; width: 100%; box-sizing: border-box; }}
            button {{ background: #238636; color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-size: 1em; margin-top: 8px; }}
            button:hover {{ background: #2ea043; }}
            .note {{ color: #8b949e; font-size: 0.9em; }}
        </style>
    </head>
    <body>
        <h1>OmegaAgent — Voice Manager</h1>
        <p>Kokoro TTS: <span class="status {kokoro_status}">{kokoro_status}</span></p>

        <h2>Built-in Voices (Kokoro)</h2>
        <table>
            <tr><th>Voice ID</th><th>Name</th><th>Gender</th><th>Accent</th></tr>
            {kokoro_rows}
        </table>
        <p class="note">Set voice in RPi 4 <code>.env</code>: <code>TTS_VOICE=af_heart</code></p>

        <h2>Custom Voices (Fish Speech Clones)</h2>
        <table>
            <tr><th>Voice ID</th><th>Name</th><th>File</th><th>Size</th></tr>
            {custom_rows}
        </table>

        <h2>Upload Voice Reference</h2>
        <form action="/speech/voices/upload" method="post" enctype="multipart/form-data">
            <label>Voice Name:</label>
            <input type="text" name="voice_name" placeholder="e.g. my_voice" required>
            <label>Reference Audio (10-30s of clear speech, WAV or MP3):</label>
            <input type="file" name="file" accept=".wav,.mp3" required>
            <button type="submit">Upload Voice</button>
        </form>
        <p class="note">Upload a short audio clip of the voice you want to clone. Fish Speech will use it as a reference for voice synthesis.</p>
    </body>
    </html>
    """


@router.post("/voices/upload")
async def upload_voice_reference(
    voice_name: str = "",
    file: UploadFile = File(...),
):
    """Upload a reference audio file for Fish Speech voice cloning.

    The audio should be 10-30 seconds of clear speech.
    """
    import re

    if not voice_name:
        voice_name = Path(file.filename or "custom_voice").stem

    # Sanitize name
    voice_name = re.sub(r"[^\w-]", "_", voice_name.lower().strip())

    ext = Path(file.filename or "audio.wav").suffix.lower()
    if ext not in (".wav", ".mp3"):
        raise HTTPException(status_code=400, detail="Only WAV and MP3 files are supported.")

    audio_bytes = await file.read()
    if len(audio_bytes) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(status_code=400, detail="File too large (max 10MB).")

    out_path = VOICE_DIR / f"{voice_name}{ext}"
    out_path.write_bytes(audio_bytes)
    logger.info("Voice reference saved: %s (%d bytes)", out_path.name, len(audio_bytes))

    return HTMLResponse(
        f'<html><body style="font-family:sans-serif;background:#0d1117;color:#c9d1d9;padding:40px">'
        f'<h2>Voice uploaded!</h2>'
        f'<p>Saved as <code>fish:{voice_name}</code></p>'
        f'<p>Use it with: <code>TTS_VOICE=fish:{voice_name}</code> in your RPi .env</p>'
        f'<a href="/speech/voices/manage" style="color:#58a6ff">← Back to Voice Manager</a>'
        f'</body></html>'
    )
