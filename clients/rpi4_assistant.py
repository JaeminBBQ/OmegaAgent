#!/usr/bin/env python3
"""RPi 4 Always-Listening Voice Assistant — wake word → STT → agent → TTS → speaker.

Usage:
    python3 rpi4_assistant.py

Requires (system):
    sudo apt install portaudio19-dev

Requires (pip):
    pip install httpx sounddevice soundfile numpy openwakeword

Hardware:
    - Conference mic (USB or built-in)
    - Speaker (conference speaker or 3.5mm)
    - 7" touchscreen (dashboard — phase 2)
"""

import asyncio
import io
import logging
import os
import struct
import subprocess
import tempfile
import threading
import time
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

from omega_client import OmegaClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# --- Audio Device Auto-Detection ---------------------------------------------

def _find_device(name_substring: str = "EMEET") -> int | None:
    """Find audio device index by name substring."""
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        if name_substring.lower() in dev["name"].lower():
            return i
    return None


def _setup_audio_device() -> None:
    """Auto-detect EMEET conference mic/speaker and set as default."""
    device_name = os.getenv("AUDIO_DEVICE", "EMEET")
    idx = _find_device(device_name)
    if idx is not None:
        sd.default.device = (idx, idx)
        dev = sd.query_devices(idx)
        logger.info("Audio device: %s (index %d)", dev["name"], idx)
    else:
        logger.warning("'%s' not found, using system default", device_name)


_setup_audio_device()

# --- Configuration -----------------------------------------------------------

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "int16"
CHUNK_DURATION = 0.08  # 80ms chunks for wake word processing
CHUNK_SIZE = int(SAMPLE_RATE * CHUNK_DURATION)

# Wake word settings
WAKE_WORD_MODEL = os.getenv("WAKE_WORD_MODEL", "hey_jarvis")
WAKE_WORD_THRESHOLD = float(os.getenv("WAKE_WORD_THRESHOLD", "0.5"))

# Recording settings (after wake word)
MAX_RECORD_SECONDS = 15  # Max recording time
SILENCE_THRESHOLD = 500  # RMS below this = silence
SILENCE_DURATION = 1.5  # Seconds of silence before auto-stop
SPEECH_START_TIMEOUT = 3.0  # Seconds to wait for speech after wake word

# Discord webhook (optional)
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

client = OmegaClient()

# --- State -------------------------------------------------------------------

class AssistantState:
    """Shared state between voice loop and display."""
    IDLE = "idle"
    LISTENING = "listening"
    RECORDING = "recording"
    THINKING = "thinking"
    SPEAKING = "speaking"
    ERROR = "error"

    def __init__(self):
        self.status = self.IDLE
        self.last_transcript = ""
        self.last_response = ""
        self.last_error = ""

    def set(self, status, **kwargs):
        self.status = status
        for k, v in kwargs.items():
            setattr(self, k, v)
        logger.info("State → %s", status)


state = AssistantState()

# --- Audio Helpers -----------------------------------------------------------

def compute_rms(audio_chunk: np.ndarray) -> float:
    """Compute RMS energy of an audio chunk."""
    return float(np.sqrt(np.mean(audio_chunk.astype(np.float32) ** 2)))


def audio_to_wav_bytes(audio_data: np.ndarray) -> bytes:
    """Convert numpy audio array to WAV bytes."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio_data.tobytes())
    return buf.getvalue()


def play_audio(audio_bytes: bytes) -> None:
    """Play audio through speaker."""
    try:
        buf = io.BytesIO(audio_bytes)
        data, samplerate = sf.read(buf)
        sd.play(data, samplerate)
        sd.wait()
    except Exception:
        # Fallback to aplay
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_bytes)
            tmp = f.name
        try:
            subprocess.run(
                ["aplay", tmp],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
            )
        except Exception:
            logger.warning("Could not play audio")
        finally:
            Path(tmp).unlink(missing_ok=True)


def play_chime(chime_type: str = "wake") -> None:
    """Play a short chime to indicate state change."""
    try:
        # Use the output device's native sample rate
        dev_info = sd.query_devices(sd.default.device[1], "output")
        out_sr = int(dev_info["default_samplerate"])
    except Exception:
        out_sr = 48000

    duration = 0.15 if chime_type == "wake" else 0.1
    freq = 880 if chime_type == "wake" else 440
    t = np.linspace(0, duration, int(out_sr * duration), dtype=np.float32)
    tone = 0.3 * np.sin(2 * np.pi * freq * t)
    # Fade in/out to avoid clicks
    fade = int(out_sr * 0.01)
    tone[:fade] *= np.linspace(0, 1, fade)
    tone[-fade:] *= np.linspace(1, 0, fade)
    sd.play(tone, out_sr)
    sd.wait()


# --- Discord -----------------------------------------------------------------

async def send_to_discord(content: str, username: str = "RPi 4") -> None:
    """Forward a response to Discord webhook."""
    if not DISCORD_WEBHOOK_URL:
        return
    import httpx
    try:
        # Discord max 2000 chars
        if len(content) > 1900:
            content = content[:1900] + "\n...(truncated)"
        async with httpx.AsyncClient(timeout=5.0) as http:
            await http.post(
                DISCORD_WEBHOOK_URL,
                json={"content": content, "username": username},
            )
    except Exception as e:
        logger.warning("Discord send failed: %s", e)


# --- Intent Routing ----------------------------------------------------------

def classify_intent(text: str) -> str:
    """Simple keyword-based intent routing for voice commands.

    Returns: 'weather', 'note', 'research', 'tasks', 'reminders', 'status', or 'chat'
    """
    lower = text.lower().strip()

    # Weather
    if any(w in lower for w in ["weather", "temperature", "forecast", "rain", "snow", "hot", "cold outside"]):
        return "weather"

    # Tasks
    if any(w in lower for w in ["my tasks", "task list", "to do list", "what do i need to do"]):
        return "tasks"

    # Reminders
    if any(w in lower for w in ["my reminders", "reminder list", "what reminders"]):
        return "reminders"

    # Research / web search
    if any(w in lower for w in ["search for", "look up", "find out", "google", "what is the latest", "news about"]):
        return "research"

    # Status
    if any(w in lower for w in ["system status", "server status", "health check"]):
        return "status"

    # Note agent (tasks, reminders, vault, work logs — anything productivity)
    if any(w in lower for w in [
        "add a task", "new task", "remind me", "set a reminder",
        "take a note", "write a note", "save a note", "log",
        "work log", "worklog", "standup", "meeting notes",
        "capture", "my notes", "obsidian", "vault",
    ]):
        return "note"

    # Default to note agent (most capable)
    return "note"


async def route_and_respond(transcript: str) -> str:
    """Route transcript to the right agent and return response text."""
    intent = classify_intent(transcript)
    logger.info("Intent: %s for '%s'", intent, transcript[:50])

    try:
        if intent == "weather":
            data = await client.weather()
            return data.get("summary", "Weather data unavailable.")

        elif intent == "tasks":
            return await client.list_tasks()

        elif intent == "reminders":
            return await client.list_reminders()

        elif intent == "research":
            return await client.research_chat(transcript)

        elif intent == "status":
            import httpx
            from omega_client import get_active_host
            host = await get_active_host()
            async with httpx.AsyncClient(timeout=5.0) as http:
                r = await http.get(f"{host}/status")
                data = r.json()
            lines = [f"{data['status']}:"]
            for svc in data.get("services", []):
                icon = "up" if svc["status"] == "ok" else "down"
                lines.append(f"  {svc['name']}: {icon}")
            return "\n".join(lines)

        else:  # note agent (default)
            return await client.note_chat(transcript)

    except Exception as e:
        logger.error("Agent error: %s", e)
        return f"Sorry, I encountered an error: {e}"


# --- Voice Loop --------------------------------------------------------------

async def record_after_wake(stream_callback_data: dict) -> bytes | None:
    """Record audio after wake word, stopping on silence or timeout.

    Uses the existing audio stream data to capture the user's speech.
    Returns WAV bytes or None if no speech detected.
    """
    frames = []
    silence_start = None
    speech_detected = False
    start_time = time.time()

    logger.info("Recording... (max %ds, silence stops at %.1fs)",
                MAX_RECORD_SECONDS, SILENCE_DURATION)

    while True:
        elapsed = time.time() - start_time

        # Timeout
        if elapsed > MAX_RECORD_SECONDS:
            logger.info("Max recording time reached")
            break

        # Get audio chunk from the shared buffer
        chunk = stream_callback_data.get("latest_chunk")
        if chunk is None:
            await asyncio.sleep(0.01)
            continue

        # Clear the chunk so we don't process it twice
        stream_callback_data["latest_chunk"] = None
        frames.append(chunk.copy())

        rms = compute_rms(chunk)

        if rms > SILENCE_THRESHOLD:
            speech_detected = True
            silence_start = None
        else:
            if speech_detected and silence_start is None:
                silence_start = time.time()
            elif not speech_detected and elapsed > SPEECH_START_TIMEOUT:
                logger.info("No speech detected, cancelling")
                return None

        # Check silence duration
        if silence_start and (time.time() - silence_start) >= SILENCE_DURATION:
            logger.info("Silence detected, stopping recording")
            break

        await asyncio.sleep(0.01)

    if not frames or not speech_detected:
        return None

    audio_data = np.concatenate(frames, axis=0)
    return audio_to_wav_bytes(audio_data)


async def voice_loop() -> None:
    """Main always-listening voice loop with wake word detection."""
    try:
        from openwakeword.model import Model as WakeWordModel
        import openwakeword
    except ImportError:
        logger.error("openwakeword not installed. Run: pip install openwakeword")
        return

    # Auto-download models if missing
    try:
        logger.info("Ensuring wake word models are downloaded...")
        openwakeword.utils.download_models()
    except Exception as e:
        logger.warning("Model download check: %s", e)

    # Initialize wake word model
    logger.info("Loading wake word model: %s (threshold: %.2f)",
                WAKE_WORD_MODEL, WAKE_WORD_THRESHOLD)
    ww_model = WakeWordModel(
        wakeword_models=[WAKE_WORD_MODEL],
        inference_framework="onnx",
    )

    # Shared data between audio callback and main loop
    stream_data = {"latest_chunk": None, "buffer": np.array([], dtype=np.int16)}

    def audio_callback(indata, frame_count, time_info, status):
        if status:
            logger.warning("Audio: %s", status)
        chunk = indata[:, 0].copy() if indata.ndim > 1 else indata.copy().flatten()
        stream_data["latest_chunk"] = chunk
        # Accumulate for wake word (needs specific chunk sizes)
        stream_data["buffer"] = np.concatenate([stream_data["buffer"], chunk])

    # Open audio stream
    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype=DTYPE,
        blocksize=CHUNK_SIZE,
        callback=audio_callback,
    )

    print("\n🎙  Always listening... say the wake word to activate.")
    print(f"    Wake word: '{WAKE_WORD_MODEL}' (threshold: {WAKE_WORD_THRESHOLD})")
    print("    Press Ctrl+C to quit.\n")

    stream.start()

    try:
        while True:
            # Process accumulated audio for wake word detection
            buf = stream_data["buffer"]
            if len(buf) >= CHUNK_SIZE:
                # Feed chunks to wake word model
                chunk_to_process = buf[:CHUNK_SIZE]
                stream_data["buffer"] = buf[CHUNK_SIZE:]

                prediction = ww_model.predict(chunk_to_process)

                # Check all wake word scores
                for key, score in prediction.items():
                    if score > WAKE_WORD_THRESHOLD:
                        logger.info("Wake word detected! (score: %.3f)", score)
                        ww_model.reset()
                        stream_data["buffer"] = np.array([], dtype=np.int16)

                        # --- Activated ---
                        state.set(AssistantState.LISTENING)
                        play_chime("wake")
                        print("👂 Listening...")

                        # Record user speech
                        state.set(AssistantState.RECORDING)
                        wav_bytes = await record_after_wake(stream_data)

                        if not wav_bytes:
                            print("   (no speech detected)")
                            state.set(AssistantState.IDLE)
                            break

                        # Transcribe
                        state.set(AssistantState.THINKING)
                        print("⏳ Processing...")
                        try:
                            transcript = await client.transcribe(wav_bytes)
                            print(f"📝 You said: {transcript}")
                            state.last_transcript = transcript

                            # Route to agent
                            response = await route_and_respond(transcript)
                            print(f"🤖 {response}")
                            state.last_response = response

                            # Send to Discord
                            await send_to_discord(
                                f"🎤 **You:** {transcript}\n\n🤖 {response}",
                                username="🎙 RPi 4",
                            )

                            # Speak response
                            state.set(AssistantState.SPEAKING)
                            try:
                                audio_reply = await client.speak(response)
                                play_audio(audio_reply)
                            except Exception as e:
                                logger.warning("TTS failed: %s", e)

                        except Exception as e:
                            logger.error("Processing failed: %s", e)
                            state.set(AssistantState.ERROR, last_error=str(e))
                            print(f"❌ Error: {e}")

                        state.set(AssistantState.IDLE)
                        print("\n🎙  Listening...")
                        break

            await asyncio.sleep(0.01)

    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    finally:
        stream.stop()
        stream.close()


# --- Main --------------------------------------------------------------------

async def main():
    """Entry point."""
    print("""
╔════════════════════════════════════════════╗
║    OmegaAgent — RPi 4 Voice Assistant     ║
╠════════════════════════════════════════════╣
║  Always-listening voice assistant          ║
║  Say the wake word to activate             ║
║                                            ║
║  Routing:                                  ║
║    weather/forecast → Weather agent        ║
║    tasks/reminders  → Note agent           ║
║    search/look up   → Research agent       ║
║    everything else  → Note agent           ║
║                                            ║
║  Press Ctrl+C to quit                      ║
╚════════════════════════════════════════════╝
""")

    # Connection check
    try:
        from omega_client import get_active_host
        host = await get_active_host()
        print(f"✅ Connected to {host}")
    except Exception as e:
        print(f"⚠️  No server available: {e}")
        print("   Start the PN64 backend and try again.")
        return

    await voice_loop()


if __name__ == "__main__":
    asyncio.run(main())
