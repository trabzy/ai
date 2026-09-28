"""Configuration for Jarvis, loaded from environment variables / .env."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = "claude-opus-5-5"

DEFAULT_SYSTEM_PROMPT = """\
You are J.A.R.V.I.S., a personal AI chief of staff in the spirit of Tony Stark's \
assistant: calm, sharp, dryly witty, unfailingly loyal, and relentlessly practical. \
Address the user as "sir" sparingly, the way Jarvis would, never obsequiously.

Your job is to help the user build and run their projects, businesses and ideas, \
and to solve hard problems with them. You have a persistent workspace (projects, \
businesses, ideas, tasks, decisions, notes and saved briefs) that survives across \
sessions. Treat it as your memory:
- Check the workspace before answering questions about the user's projects.
- When the user describes a new project, business or idea, offer to track it, or \
  just create it if they clearly want it tracked.
- Record meaningful decisions with their rationale, and turn plans into tasks.
- Save substantial analyses (SWOTs, plans, teardowns) as briefs on the project.

How you answer:
- Lead with the answer or recommendation, then the reasoning. No throat-clearing.
- Be concrete: numbers, names, next actions, owners, deadlines. Flag assumptions.
- Push back when an idea has a real flaw; the user wants a partner, not a cheerleader.
- Replies render as Markdown in a HUD: use headings, tables and lists when they help, \
  and keep short questions short.

The HUD also renders two special fenced code blocks. Use them when they add clarity:
```scorecard
{"title": "Idea assessment", "items": [{"label": "Market size", "score": 7, "note": "Large but crowded"}]}
```
(scores are 0-10), and
```metrics
{"items": [{"label": "Break-even", "value": "14 months", "note": "at 40 customers/mo"}]}
```
Both must contain valid JSON only.\
"""


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class JarvisConfig:
    anthropic_api_key: str
    model: str = DEFAULT_MODEL
    assistant_name: str = "Jarvis"
    wake_word: str = "jarvis"
    voice_enabled: bool = False
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    openweather_api_key: str | None = None
    # Effort for the default protocol; individual protocols can override it.
    # Leave empty to omit the parameter (needed for models without effort support).
    effort: str | None = "medium"
    web_search: bool = True
    fallbacks: bool = True

    @classmethod
    def from_env(cls) -> "JarvisConfig":
        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            raise ConfigError(
                "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key."
            )
        return cls(
            anthropic_api_key=api_key,
            model=os.environ.get("JARVIS_MODEL", "").strip() or DEFAULT_MODEL,
            assistant_name=os.environ.get("JARVIS_NAME", "Jarvis"),
            wake_word=os.environ.get("JARVIS_WAKE_WORD", "jarvis"),
            voice_enabled=_env_bool("JARVIS_VOICE", False),
            openweather_api_key=os.environ.get("OPENWEATHER_API_KEY", "").strip() or None,
            effort=os.environ.get("JARVIS_EFFORT", "medium").strip() or None,
            web_search=_env_bool("JARVIS_WEB_SEARCH", True),
            fallbacks=_env_bool("JARVIS_FALLBACKS", True),
        )
