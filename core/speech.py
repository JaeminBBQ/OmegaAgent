"""Speech client — Whisper STT + Fish Speech / Kokoro TTS.

Proxies requests to the desktop GPU server at 172.16.0.94.
All three services expose OpenAI-compatible endpoints.
"""

import logging
from enum import Enum

import httpx

from core.config import FISH_TTS_URL, KOKORO_TTS_URL, WHISPER_URL

logger = logging.getLogger(__name__)


class TTSProvider(str, Enum):
    FISH = "fish"       # High quality, voice cloning, ~2-3s latency
    KOKORO = "kokoro"   # Fast, lightweight, ~82M params, instant


class SpeechClient:
    """Async wrapper for STT and TTS services on the desktop GPU."""

    def __init__(
        self,
        whisper_url: str | None = None,
        fish_tts_url: str | None = None,
        kokoro_tts_url: str | None = None,
    ) -> None:
        self._whisper_url = (whisper_url or WHISPER_URL).rstrip("/")
        self._fish_url = (fish_tts_url or FISH_TTS_URL).rstrip("/")
        self._kokoro_url = (kokoro_tts_url or KOKORO_TTS_URL).rstrip("/")

    # -- STT ----------------------------------------------------------------

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str = "audio.wav",
        language: str | None = "en",
    ) -> str:
        """Transcribe audio bytes to text via Whisper."""
        url = f"{self._whisper_url}/v1/audio/transcriptions"
        files = {"file": (filename, audio_bytes, "audio/wav")}
        data: dict = {}
        if language:
            data["language"] = language

        logger.debug("STT request: %d bytes to %s", len(audio_bytes), url)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, files=files, data=data)
            resp.raise_for_status()
            result = resp.json()

        text = result.get("text", "").strip()
        logger.info("STT result: %d chars", len(text))
        return text

    # -- TTS ----------------------------------------------------------------

    async def speak(
        self,
        text: str,
        provider: TTSProvider = TTSProvider.KOKORO,
        voice: str = "af_heart",
        format: str = "wav",
        reference_audio: bytes | None = None,
        reference_text: str | None = None,
    ) -> bytes:
        """Generate speech audio from text.

        Args:
            text: Text to synthesize.
            provider: KOKORO (fast, default) or FISH (high quality).
            voice: Voice ID (Kokoro only).
            format: Output format (wav, mp3).
            reference_audio: Raw audio bytes for Fish Speech voice cloning.
            reference_text: Transcript of the reference audio (improves clone quality).

        Returns:
            Raw audio bytes.
        """
        if provider == TTSProvider.KOKORO:
            url = f"{self._kokoro_url}/v1/tts"
            payload = {"text": text, "voice": voice}
            logger.debug("TTS request (kokoro): %d chars to %s", len(text), url)
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
        else:
            url = f"{self._fish_url}/v1/tts"
            if reference_audio:
                # Voice cloning: send reference audio + transcript as multipart
                form_data = {"text": text, "format": format}
                if reference_text:
                    form_data["reference_text"] = reference_text
                logger.debug("TTS request (fish clone): %d chars, %d ref bytes, ref_text=%s",
                             len(text), len(reference_audio), bool(reference_text))
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post(
                        url,
                        data=form_data,
                        files={"reference_audio": ("reference.wav", reference_audio, "audio/wav")},
                    )
                    resp.raise_for_status()
            else:
                payload = {"text": text, "format": format}
                logger.debug("TTS request (fish): %d chars to %s", len(text), url)
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(url, json=payload)
                    resp.raise_for_status()

        logger.info("TTS result (%s): %d bytes audio", provider, len(resp.content))
        return resp.content

    # -- Health checks -------------------------------------------------------

    async def health_check_whisper(self) -> bool:
        """Check if Whisper STT is reachable."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._whisper_url}/v1/health")
                return resp.status_code == 200
        except Exception as exc:
            logger.warning("Whisper health check failed: %s", exc)
            return False

    async def health_check_tts(self, provider: TTSProvider = TTSProvider.KOKORO) -> bool:
        """Check if a TTS service is reachable."""
        url = self._kokoro_url if provider == TTSProvider.KOKORO else self._fish_url
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{url}/v1/health")
                return resp.status_code == 200
        except Exception as exc:
            logger.warning("%s TTS health check failed: %s", provider, exc)
            return False
