"""OmegaAgent client library — used by RPi 4 and RPi 400.

Handles server discovery (failover), chat, STT, TTS, and agent calls.
This is the only dependency RPi clients need besides httpx.
"""

import asyncio
import logging
import time
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

PRIMARY = "http://172.16.0.200:8080"    # PN64
FALLBACK = "http://172.16.0.94:8080"    # Desktop

# Cache the active host for 30 seconds
_active_host: str | None = None
_host_checked_at: float = 0.0
HOST_CACHE_TTL = 30.0


async def get_active_host() -> str:
    """Discover which server is up. Caches result for 30s."""
    global _active_host, _host_checked_at

    if _active_host and (time.time() - _host_checked_at) < HOST_CACHE_TTL:
        return _active_host

    for host in [PRIMARY, FALLBACK]:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(f"{host}/status")
                if r.status_code == 200 and r.json().get("status") in ["ok", "degraded"]:
                    _active_host = host
                    _host_checked_at = time.time()
                    logger.info("Active host: %s", host)
                    return host
        except Exception:
            logger.debug("Host %s unreachable", host)

    raise RuntimeError("No OmegaAgent servers available")


def _clear_host_cache():
    """Force re-discovery on next call."""
    global _active_host, _host_checked_at
    _active_host = None
    _host_checked_at = 0.0


class OmegaClient:
    """Async client for all OmegaAgent API interactions."""

    def __init__(self) -> None:
        self._host: str | None = None

    async def _get_host(self) -> str:
        """Get the active server host."""
        return await get_active_host()

    # -- Chat ---------------------------------------------------------------

    async def ask(self, message: str, system: str | None = None) -> str:
        """Send a message to Haiku, get a text reply."""
        host = await self._get_host()
        payload: dict = {"message": message}
        if system:
            payload["system"] = system

        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(f"{host}/chat/ask", json=payload)
            r.raise_for_status()
            return r.json()["reply"]

    # -- Speech -------------------------------------------------------------

    async def transcribe(self, audio_bytes: bytes, filename: str = "audio.wav") -> str:
        """Send audio bytes, get transcribed text back."""
        host = await self._get_host()
        files = {"file": (filename, audio_bytes, "audio/wav")}

        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(f"{host}/speech/transcribe", files=files)
            r.raise_for_status()
            return r.json()["text"]

    async def transcribe_file(self, path: str | Path) -> str:
        """Transcribe an audio file from disk."""
        audio_bytes = Path(path).read_bytes()
        return await self.transcribe(audio_bytes, Path(path).name)

    async def speak(
        self, text: str, provider: str = "kokoro", voice: str = "af_heart"
    ) -> bytes:
        """Generate TTS audio from text. Returns WAV bytes."""
        host = await self._get_host()
        payload = {"text": text, "provider": provider, "voice": voice}

        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(f"{host}/speech/tts", json=payload)
            r.raise_for_status()
            return r.content

    async def speak_to_file(
        self, text: str, path: str | Path, provider: str = "kokoro", voice: str = "af_heart"
    ) -> Path:
        """Generate TTS and save to a file. Returns the path."""
        audio = await self.speak(text, provider=provider, voice=voice)
        out = Path(path)
        out.write_bytes(audio)
        return out

    # -- Agents -------------------------------------------------------------

    async def weather(
        self, latitude: float = 39.5296, longitude: float = -119.8138, location: str = "Reno, NV"
    ) -> dict:
        """Run the weather agent and return structured results."""
        host = await self._get_host()
        payload = {"latitude": latitude, "longitude": longitude, "location_name": location}

        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(f"{host}/agents/weather/run", json=payload)
            r.raise_for_status()
            return r.json()

    # -- Notes --------------------------------------------------------------

    async def note_chat(self, message: str, thread_id: str | None = None) -> str:
        """Conversational note-taking with the LangChain agent."""
        host = await self._get_host()
        payload: dict = {"message": message}
        if thread_id:
            payload["thread_id"] = thread_id

        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(f"{host}/notes/chat", json=payload)
            r.raise_for_status()
            return r.json()["reply"]

    async def quick_task(self, description: str, priority: str = "medium") -> str:
        """Add a task directly."""
        host = await self._get_host()
        payload = {"description": description, "priority": priority}

        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(f"{host}/notes/task", json=payload)
            r.raise_for_status()
            return r.json()["result"]

    async def quick_remind(self, message: str, when: str) -> str:
        """Set a reminder directly."""
        host = await self._get_host()
        payload = {"message": message, "when": when}

        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(f"{host}/notes/remind", json=payload)
            r.raise_for_status()
            return r.json()["result"]

    async def quick_capture(self, text: str) -> str:
        """Quick-capture a note to today's daily file."""
        host = await self._get_host()

        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(f"{host}/notes/capture", json={"text": text})
            r.raise_for_status()
            return r.json()["result"]

    async def quick_worklog(self, entry: str) -> str:
        """Add a work log entry."""
        host = await self._get_host()

        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(f"{host}/notes/worklog", json={"entry": entry})
            r.raise_for_status()
            return r.json()["result"]

    async def list_tasks(self) -> str:
        """List all pending tasks."""
        host = await self._get_host()

        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{host}/notes/tasks")
            r.raise_for_status()
            return r.json()["result"]

    async def list_reminders(self) -> str:
        """List all upcoming reminders."""
        host = await self._get_host()

        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{host}/notes/reminders")
            r.raise_for_status()
            return r.json()["result"]

    # -- Full pipelines -----------------------------------------------------

    async def voice_ask(self, audio_bytes: bytes) -> tuple[str, bytes]:
        """Full voice pipeline: audio in → STT → Haiku → TTS → audio out.

        Returns:
            (text_reply, audio_reply_bytes)
        """
        text = await self.transcribe(audio_bytes)
        logger.info("User said: %s", text)

        reply = await self.ask(text)
        logger.info("Haiku replied: %s", reply[:80])

        audio = await self.speak(reply)
        return reply, audio

    async def voice_weather(self, audio_bytes: bytes) -> tuple[dict, bytes]:
        """Voice pipeline for weather: audio in → STT → weather agent → TTS summary.

        Returns:
            (weather_data, audio_summary_bytes)
        """
        text = await self.transcribe(audio_bytes)
        logger.info("User said: %s", text)

        data = await self.weather()
        summary = data.get("summary", "Weather data unavailable")

        audio = await self.speak(summary)
        return data, audio
