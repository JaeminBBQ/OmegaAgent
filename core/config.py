"""Centralized configuration loaded from environment variables."""

import os

from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    """Return an env var or raise with a clear message."""
    val = os.getenv(key)
    if not val:
        raise RuntimeError(f"Missing required environment variable: {key}")
    return val


# --- Supabase ---
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")

# --- Anthropic ---
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

# --- Serper ---
SERPER_API_KEY: str = os.getenv("SERPER_API_KEY", "")

# --- Desktop GPU Server (STT/TTS at 172.16.0.94) ---
WHISPER_URL: str = os.getenv("WHISPER_URL", "http://172.16.0.94:8000")
FISH_TTS_URL: str = os.getenv("FISH_TTS_URL", "http://172.16.0.94:8080")
KOKORO_TTS_URL: str = os.getenv("KOKORO_TTS_URL", "http://172.16.0.94:8081")

# --- Obsidian Vault ---
OBSIDIAN_VAULT_PATH: str = os.getenv("OBSIDIAN_VAULT_PATH", "./vault")

# --- Discord (notifications) ---
DISCORD_WEBHOOK_URL: str = os.getenv("DISCORD_WEBHOOK_URL", "")

# --- General ---
DEFAULT_TIMEZONE: str = os.getenv("DEFAULT_TIMEZONE", "America/Los_Angeles")
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
