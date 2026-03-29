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

# --- Desktop GPU Server (STT/TTS) ---
GPU_SERVER_URL: str = os.getenv("GPU_SERVER_URL", "http://desktop:5000")

# --- General ---
DEFAULT_TIMEZONE: str = os.getenv("DEFAULT_TIMEZONE", "America/Los_Angeles")
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
