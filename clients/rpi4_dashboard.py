#!/usr/bin/env python3
"""RPi 4 Voice Dashboard — mic → STT → agents/chat → TTS → speaker + display.

Usage:
    python3 rpi4_dashboard.py

Requires:
    pip install httpx sounddevice soundfile numpy

Hardware:
    - USB mic or conference speaker with mic
    - 7" touchscreen (for display output)
    - Speaker / conference speaker for TTS playback
"""

import asyncio
import io
import logging
import subprocess
import tempfile
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

client = OmegaClient()

# Audio recording settings
SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "int16"

HELP_TEXT = """
╔════════════════════════════════════════╗
║  OmegaAgent — RPi 4 Voice Dashboard   ║
╠════════════════════════════════════════╣
║  Press ENTER to start recording       ║
║  Press ENTER again to stop & send     ║
║                                       ║
║  Commands:                            ║
║    /weather  — get Reno weather       ║
║    /status   — check server health    ║
║    /text     — type instead of speak  ║
║    /quit     — exit                   ║
╚════════════════════════════════════════╝
"""


def record_audio() -> bytes:
    """Record audio from mic until user presses Enter. Returns WAV bytes."""
    print("🎤 Recording... (press ENTER to stop)")
    frames = []
    recording = True

    def callback(indata, frame_count, time_info, status):
        if status:
            logger.warning("Audio status: %s", status)
        if recording:
            frames.append(indata.copy())

    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype=DTYPE,
        callback=callback,
    )

    stream.start()
    input()  # Wait for Enter to stop
    recording = False
    stream.stop()
    stream.close()

    if not frames:
        return b""

    audio_data = np.concatenate(frames, axis=0)

    # Convert to WAV bytes
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio_data.tobytes())

    return buf.getvalue()


def play_audio(audio_bytes: bytes) -> None:
    """Play WAV audio through speakers."""
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
            subprocess.run(["aplay", tmp], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        except Exception:
            logger.warning("Could not play audio")
        finally:
            Path(tmp).unlink(missing_ok=True)


def display_weather(data: dict) -> None:
    """Pretty-print weather data to the terminal/touchscreen."""
    current = data["current"]
    print(f"\n{'═'*50}")
    print(f"  🌡  {data['location']}")
    print(f"{'═'*50}")
    print(f"  Now: {current['temperature_f']}°F, {current['weather_description']}")
    print(f"  Feels like: {current['feels_like_f']}°F")
    print(f"  Wind: {current['wind_speed_mph']} mph")
    print(f"  Humidity: {current['humidity_pct']}%")

    if data.get("alerts"):
        print(f"\n  ⚠️  ALERTS:")
        for alert in data["alerts"]:
            print(f"     {alert['severity'].upper()}: {alert['message']}")

    print(f"\n  📅 Forecast:")
    for day in data.get("forecast", [])[:5]:
        print(f"     {day['date']}: {day['low_f']}–{day['high_f']}°F, {day['weather_description']}")

    summary = data.get("summary", "")
    if summary:
        print(f"\n  📋 {summary}")
    print(f"{'═'*50}\n")


async def handle_voice() -> None:
    """Record → STT → Chat → TTS pipeline."""
    audio_bytes = record_audio()
    if not audio_bytes:
        print("No audio recorded.")
        return

    print("⏳ Transcribing...")
    try:
        reply, audio_reply = await client.voice_ask(audio_bytes)
        print(f"\n🤖 {reply}")
        play_audio(audio_reply)
    except Exception as e:
        print(f"❌ Error: {e}")


async def handle_voice_weather() -> None:
    """Record voice → weather agent → speak summary."""
    print("\n⏳ Fetching weather...")
    try:
        data = await client.weather()
        display_weather(data)

        summary = data.get("summary", "Weather unavailable")
        audio = await client.speak(summary)
        play_audio(audio)
    except Exception as e:
        print(f"❌ Weather failed: {e}")


async def handle_text_input() -> None:
    """Type a message instead of speaking."""
    message = input("you (text) > ").strip()
    if not message:
        return

    print("⏳ Thinking...")
    try:
        reply = await client.ask(message)
        print(f"\n🤖 {reply}")
        audio = await client.speak(reply)
        play_audio(audio)
    except Exception as e:
        print(f"❌ Error: {e}")


async def main() -> None:
    """Main dashboard loop."""
    print(HELP_TEXT)

    # Connection check
    try:
        from omega_client import get_active_host
        host = await get_active_host()
        print(f"✅ Connected to {host}\n")
    except Exception as e:
        print(f"⚠️  No server available: {e}\n")

    while True:
        try:
            action = input("Press ENTER to speak, or type a command > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n👋 Goodbye!")
            break

        if action == "/quit":
            print("👋 Goodbye!")
            break
        elif action == "/weather":
            await handle_voice_weather()
        elif action == "/status":
            from omega_client import get_active_host
            import httpx
            try:
                host = await get_active_host()
                async with httpx.AsyncClient(timeout=5.0) as http:
                    r = await http.get(f"{host}/status")
                    data = r.json()
                print(f"\n🖥  {host} — {data['status']}")
                for svc in data.get("services", []):
                    icon = "✅" if svc["status"] == "ok" else "❌"
                    print(f"   {icon} {svc['name']}: {svc['latency_ms']}ms")
            except Exception as e:
                print(f"❌ {e}")
        elif action == "/text":
            await handle_text_input()
        elif action == "":
            await handle_voice()
        else:
            # Treat as text input
            print("⏳ Thinking...")
            try:
                reply = await client.ask(action)
                print(f"\n🤖 {reply}")
                audio = await client.speak(reply)
                play_audio(audio)
            except Exception as e:
                print(f"❌ {e}")

        print()


if __name__ == "__main__":
    asyncio.run(main())
