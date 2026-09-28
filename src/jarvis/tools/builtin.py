"""Built-in tools Jarvis can call while answering a request."""

from __future__ import annotations

import ast
import datetime
import json
import operator
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from .registry import ToolRegistry

registry = ToolRegistry()

DATA_DIR = Path(os.environ.get("JARVIS_DATA_DIR", str(Path.home() / ".jarvis")))
NOTES_FILE = DATA_DIR / "notes.json"
REMINDERS_FILE = DATA_DIR / "reminders.json"


def _load_json_list(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def _save_json_list(path: Path, items: list[str]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, indent=2))


# ---------------------------------------------------------------------------
# Time & date
# ---------------------------------------------------------------------------


@registry.register(
    name="get_current_time",
    description="Get the current time, optionally in a specific IANA timezone (e.g. 'America/New_York').",
    input_schema={
        "type": "object",
        "properties": {
            "timezone": {
                "type": "string",
                "description": "IANA timezone name. Defaults to the system's local timezone.",
            }
        },
    },
)
def get_current_time(timezone: str | None = None) -> str:
    now = datetime.datetime.now(ZoneInfo(timezone)) if timezone else datetime.datetime.now()
    return now.strftime("%H:%M:%S")


@registry.register(
    name="get_current_date",
    description="Get today's date.",
    input_schema={"type": "object", "properties": {}},
)
def get_current_date() -> str:
    return datetime.date.today().isoformat()


# ---------------------------------------------------------------------------
# Calculator
# ---------------------------------------------------------------------------

_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_eval_node(node.operand))
    raise ValueError("Only basic arithmetic (+ - * / ** % //) is supported.")


@registry.register(
    name="calculate",
    description="Evaluate a basic arithmetic expression, e.g. '(3 + 4) * 2 / 7'.",
    input_schema={
        "type": "object",
        "properties": {"expression": {"type": "string", "description": "The arithmetic expression to evaluate."}},
        "required": ["expression"],
    },
)
def calculate(expression: str) -> str:
    tree = ast.parse(expression, mode="eval")
    result = _eval_node(tree.body)
    return str(result)


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------


@registry.register(
    name="take_note",
    description="Save a short note for later.",
    input_schema={
        "type": "object",
        "properties": {"text": {"type": "string", "description": "The note to save."}},
        "required": ["text"],
    },
)
def take_note(text: str) -> str:
    notes = _load_json_list(NOTES_FILE)
    notes.append(text)
    _save_json_list(NOTES_FILE, notes)
    return f"Saved note #{len(notes)}."


@registry.register(
    name="list_notes",
    description="List all saved notes.",
    input_schema={"type": "object", "properties": {}},
)
def list_notes() -> str:
    notes = _load_json_list(NOTES_FILE)
    if not notes:
        return "There are no saved notes."
    return "\n".join(f"{i + 1}. {note}" for i, note in enumerate(notes))


# ---------------------------------------------------------------------------
# Reminders
# ---------------------------------------------------------------------------


@registry.register(
    name="set_reminder",
    description="Save a reminder with what to do and when.",
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "What to be reminded about."},
            "when": {"type": "string", "description": "When the reminder is for, in plain language (e.g. 'tomorrow at 9am')."},
        },
        "required": ["text", "when"],
    },
)
def set_reminder(text: str, when: str) -> str:
    reminders = _load_json_list(REMINDERS_FILE)
    reminders.append(f"{when}: {text}")
    _save_json_list(REMINDERS_FILE, reminders)
    return f"Reminder set for {when}."


@registry.register(
    name="list_reminders",
    description="List all saved reminders.",
    input_schema={"type": "object", "properties": {}},
)
def list_reminders() -> str:
    reminders = _load_json_list(REMINDERS_FILE)
    if not reminders:
        return "There are no saved reminders."
    return "\n".join(f"{i + 1}. {reminder}" for i, reminder in enumerate(reminders))


# ---------------------------------------------------------------------------
# Weather (requires OPENWEATHER_API_KEY)
# ---------------------------------------------------------------------------


@registry.register(
    name="get_weather",
    description="Get the current weather for a city.",
    input_schema={
        "type": "object",
        "properties": {"city": {"type": "string", "description": "City name, e.g. 'London'."}},
        "required": ["city"],
    },
)
def get_weather(city: str) -> str:
    api_key = os.environ.get("OPENWEATHER_API_KEY", "").strip()
    if not api_key:
        return "Weather lookups aren't configured. Set OPENWEATHER_API_KEY to enable this tool."
    response = requests.get(
        "https://api.openweathermap.org/data/2.5/weather",
        params={"q": city, "appid": api_key, "units": "metric"},
        timeout=10,
    )
    if response.status_code == 404:
        return f"I couldn't find weather data for '{city}'."
    response.raise_for_status()
    data = response.json()
    description = data["weather"][0]["description"]
    temp = data["main"]["temp"]
    feels_like = data["main"]["feels_like"]
    return f"{city}: {description}, {temp}°C (feels like {feels_like}°C)."


# ---------------------------------------------------------------------------
# Web search (DuckDuckGo instant answers, no API key required)
# ---------------------------------------------------------------------------


@registry.register(
    name="web_search",
    description="Look up a quick factual answer or summary from the web.",
    input_schema={
        "type": "object",
        "properties": {"query": {"type": "string", "description": "The search query."}},
        "required": ["query"],
    },
)
def web_search(query: str) -> str:
    response = requests.get(
        "https://api.duckduckgo.com/",
        params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()
    answer = data.get("AbstractText") or data.get("Answer")
    if answer:
        return answer
    topics = data.get("RelatedTopics") or []
    for topic in topics:
        text = topic.get("Text")
        if text:
            return text
    return f"I couldn't find a quick answer for '{query}'."
