"""Configuration for Jarvis, loaded from environment variables / .env."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

DEFAULT_SYSTEM_PROMPT = (
    "You are Jarvis, a concise and capable personal voice assistant. "
    "Keep spoken replies short and natural since they may be read aloud. "
    "Use the tools available to you whenever they let you give a more useful "
    "or accurate answer instead of guessing."
)


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


@dataclass
class JarvisConfig:
    anthropic_api_key: str
    model: str = "claude-sonnet-5"
    assistant_name: str = "Jarvis"
    wake_word: str = "jarvis"
    voice_enabled: bool = False
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    openweather_api_key: str | None = None

    @classmethod
    def from_env(cls) -> "JarvisConfig":
        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            raise ConfigError(
                "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key."
            )
        return cls(
            anthropic_api_key=api_key,
            model=os.environ.get("JARVIS_MODEL", "claude-sonnet-5"),
            assistant_name=os.environ.get("JARVIS_NAME", "Jarvis"),
            wake_word=os.environ.get("JARVIS_WAKE_WORD", "jarvis"),
            voice_enabled=os.environ.get("JARVIS_VOICE", "false").strip().lower() == "true",
            openweather_api_key=os.environ.get("OPENWEATHER_API_KEY", "").strip() or None,
        )
