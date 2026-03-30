#!/usr/bin/env python3
"""RPi 400 Work Assistant — keyboard input → Haiku → TTS output.

Usage:
    python3 rpi400_assistant.py

Requires: pip install httpx
Optional: pip install sounddevice soundfile (for TTS playback)
"""

import asyncio
import logging
import os
import subprocess
import tempfile
from pathlib import Path

import httpx
from omega_client import OmegaClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

client = OmegaClient()

# --- Discord webhook (mirrors all responses to Discord) -------------------
DISCORD_WEBHOOK_URL = os.getenv(
    "DISCORD_WEBHOOK_URL",
    "https://discord.com/api/webhooks/1487995591182258237/4lSljasHrm9EKsSpVDUR0JISbdn8R4iYZ3n1ZE4nwbYH_wUPiUNPXBdg6vK9WY1_RUjm",
)

HELP_TEXT = """
╔════════════════════════════════════════════╗
║       OmegaAgent — RPi 400 Assistant      ║
╠════════════════════════════════════════════╣
║  Notes:                                   ║
║    /note <msg>    — talk to note agent    ║
║    /task <desc>   — add a task            ║
║    /tasks         — list pending tasks    ║
║    /remind <msg> <time> — set reminder    ║
║    /reminders     — list reminders        ║
║    /worklog <msg> — add work log entry    ║
║    /capture <msg> — quick daily note      ║
║                                           ║
║  Other:                                   ║
║    /weather       — get Reno weather      ║
║    /status        — check server health   ║
║    /voice         — toggle TTS on/off     ║
║    /discord       — toggle Discord on/off ║
║    /quit          — exit                  ║
║                                           ║
║  Or just type a question for Haiku        ║
╚════════════════════════════════════════════╝
"""

tts_enabled = True
discord_enabled = True


async def send_to_discord(content: str, username: str = "RPi 400") -> None:
    """Forward a response to Discord webhook so it shows up on phone/desktop."""
    if not discord_enabled or not DISCORD_WEBHOOK_URL:
        return
    # Discord has a 2000 char limit per message
    chunks = [content[i:i + 1990] for i in range(0, len(content), 1990)]
    try:
        async with httpx.AsyncClient(timeout=5.0) as http:
            for chunk in chunks:
                await http.post(
                    DISCORD_WEBHOOK_URL,
                    json={"content": chunk, "username": username},
                )
    except Exception as e:
        logger.warning("Discord webhook failed: %s", e)


def play_audio(audio_bytes: bytes) -> None:
    """Play WAV audio. Tries aplay (ALSA), falls back to ffplay."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(audio_bytes)
        tmp_path = f.name

    try:
        # Try ALSA first (common on RPi)
        subprocess.run(
            ["aplay", tmp_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        try:
            subprocess.run(
                ["ffplay", "-nodisp", "-autoexit", tmp_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
            )
        except FileNotFoundError:
            logger.warning("No audio player found (tried aplay, ffplay)")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


async def handle_weather() -> None:
    """Fetch and display weather, optionally speak the summary."""
    print("\n⏳ Fetching weather...")
    try:
        data = await client.weather()
        current = data["current"]
        msg = f"🌡 {data['location']}: {current['temperature_f']}°F, {current['weather_description']}\n"
        msg += f"💨 Wind: {current['wind_speed_mph']} mph\n"
        msg += f"💧 Humidity: {current['humidity_pct']}%"

        if data.get("alerts"):
            msg += "\n⚠️ Alerts:"
            for alert in data["alerts"]:
                msg += f"\n   {alert['severity'].upper()}: {alert['message']}"

        summary = data.get("summary", "")
        if summary:
            msg += f"\n📋 Summary:\n{summary}"

        print(f"\n{msg}")
        await send_to_discord(msg, username="🌤 Weather")

        if tts_enabled and summary:
            audio = await client.speak(summary)
            play_audio(audio)
    except Exception as e:
        print(f"❌ Weather failed: {e}")


async def handle_status() -> None:
    """Check and display server status."""
    print("\n⏳ Checking status...")
    try:
        from omega_client import get_active_host
        import httpx

        host = await get_active_host()
        async with httpx.AsyncClient(timeout=5.0) as http:
            r = await http.get(f"{host}/status")
            data = r.json()

        print(f"\n🖥  Server: {host}")
        print(f"📊 Status: {data['status']}")
        for svc in data.get("services", []):
            icon = "✅" if svc["status"] == "ok" else "❌"
            print(f"   {icon} {svc['name']}: {svc['status']} ({svc['latency_ms']}ms)")
    except Exception as e:
        print(f"❌ Status check failed: {e}")


async def handle_note(message: str) -> None:
    """Send message to the conversational note agent."""
    print("\n⏳ Thinking...")
    try:
        reply = await client.note_chat(message)
        print(f"\n📝 {reply}")
        await send_to_discord(f"📝 **Note:** {message}\n\n{reply}", username="📝 Notes")

        if tts_enabled:
            audio = await client.speak(reply)
            play_audio(audio)
    except Exception as e:
        print(f"❌ Note agent failed: {e}")


async def handle_quick_task(description: str) -> None:
    """Add a task quickly."""
    try:
        result = await client.quick_task(description)
        print(f"\n✅ {result}")
        await send_to_discord(f"✅ {result}", username="📋 Tasks")
    except Exception as e:
        print(f"❌ Task failed: {e}")


async def handle_list_tasks() -> None:
    """List pending tasks."""
    try:
        result = await client.list_tasks()
        print(f"\n{result}")
        await send_to_discord(result, username="📋 Tasks")
    except Exception as e:
        print(f"❌ {e}")


async def handle_quick_remind(raw: str) -> None:
    """Parse '/remind <msg> <time>' and set a reminder."""
    # Try to split on last space-delimited time-like token
    parts = raw.rsplit(" ", 1)
    if len(parts) < 2:
        print("Usage: /remind <message> <time>  (e.g. /remind Call dentist 3pm)")
        return
    message, when = parts[0], parts[1]
    try:
        result = await client.quick_remind(message, when)
        print(f"\n⏰ {result}")
        await send_to_discord(f"⏰ {result}", username="⏰ Reminders")
    except Exception as e:
        print(f"❌ Reminder failed: {e}")


async def handle_list_reminders() -> None:
    """List upcoming reminders."""
    try:
        result = await client.list_reminders()
        print(f"\n{result}")
        await send_to_discord(result, username="⏰ Reminders")
    except Exception as e:
        print(f"❌ {e}")


async def handle_quick_worklog(entry: str) -> None:
    """Add a work log entry."""
    try:
        result = await client.quick_worklog(entry)
        print(f"\n📋 {result}")
        await send_to_discord(f"📋 {result}", username="💼 Work Log")
    except Exception as e:
        print(f"❌ {e}")


async def handle_quick_capture(text: str) -> None:
    """Quick capture a note."""
    try:
        result = await client.quick_capture(text)
        print(f"\n📌 {result}")
        await send_to_discord(f"📌 {result}", username="📌 Capture")
    except Exception as e:
        print(f"❌ {e}")


async def handle_chat(message: str) -> None:
    """Send message to Haiku and display/speak the reply."""
    print("\n⏳ Thinking...")
    try:
        reply = await client.ask(message)
        print(f"\n🤖 {reply}")
        await send_to_discord(f"**You:** {message}\n\n🤖 {reply}", username="🤖 Haiku")

        if tts_enabled:
            audio = await client.speak(reply)
            play_audio(audio)
    except Exception as e:
        print(f"❌ Chat failed: {e}")


async def main() -> None:
    """Main input loop."""
    global tts_enabled, discord_enabled

    print(HELP_TEXT)

    # Initial connection check
    try:
        from omega_client import get_active_host
        host = await get_active_host()
        print(f"✅ Connected to {host}\n")
    except Exception as e:
        print(f"⚠️  No server available: {e}")
        print("   Start the PN64 backend and try again.\n")

    while True:
        try:
            user_input = input("you > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n👋 Goodbye!")
            break

        if not user_input:
            continue

        if user_input == "/quit":
            print("👋 Goodbye!")
            break
        elif user_input == "/weather":
            await handle_weather()
        elif user_input == "/status":
            await handle_status()
        elif user_input == "/voice":
            tts_enabled = not tts_enabled
            state = "ON" if tts_enabled else "OFF"
            print(f"🔊 TTS is now {state}")
        elif user_input == "/discord":
            discord_enabled = not discord_enabled
            state = "ON" if discord_enabled else "OFF"
            print(f"💬 Discord is now {state}")
        elif user_input.startswith("/note "):
            msg = user_input[6:].strip()
            await handle_note(msg)
        elif user_input.startswith("/task "):
            desc = user_input[6:].strip()
            await handle_quick_task(desc)
        elif user_input == "/tasks":
            await handle_list_tasks()
        elif user_input.startswith("/remind "):
            await handle_quick_remind(user_input[8:].strip())
        elif user_input == "/reminders":
            await handle_list_reminders()
        elif user_input.startswith("/worklog "):
            entry = user_input[9:].strip()
            await handle_quick_worklog(entry)
        elif user_input.startswith("/capture "):
            text = user_input[9:].strip()
            await handle_quick_capture(text)
        elif user_input.startswith("/"):
            print(f"Unknown command: {user_input}")
        else:
            await handle_chat(user_input)

        print()


if __name__ == "__main__":
    asyncio.run(main())
