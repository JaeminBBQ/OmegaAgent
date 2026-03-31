"""Speech client — Whisper STT + Fish Speech / Kokoro TTS.

Proxies requests to the desktop GPU server at 172.16.0.94.
All three services expose OpenAI-compatible endpoints.

Fish Speech S1 Mini uses msgpack-serialized requests with
ServeReferenceAudio schema for voice cloning.
"""

import logging
from enum import Enum
import httpx
import ormsgpack

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

            # Build Fish Speech S1 Mini request (msgpack format)
            references = []
            if reference_audio:
                references.append({
                    "audio": reference_audio,
                    "text": reference_text or "",
                })
                logger.debug("TTS request (fish clone): %d chars, %d ref bytes, ref_text=%d chars",
                             len(text), len(reference_audio), len(reference_text or ""))
            else:
                logger.debug("TTS request (fish): %d chars to %s", len(text), url)

            request_data = {
                "text": text,
                "references": references,
                "reference_id": None,
                "format": format,
                "max_new_tokens": 1024,
                "chunk_length": 300,
                "top_p": 0.8,
                "repetition_penalty": 1.1,
                "temperature": 0.8,
                "streaming": False,
                "use_memory_cache": "off",
                "seed": None,
            }

            body = ormsgpack.packb(request_data)
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    url,
                    content=body,
                    headers={"content-type": "application/msgpack"},
                )
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
