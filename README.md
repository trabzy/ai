# Jarvis

A personal voice/text assistant powered by the Claude API. Talk to it with
your voice (wake word + speech-to-text + text-to-speech) or in a plain text
chat, and it can call tools — check the time, do arithmetic, save notes and
reminders, look up the weather, and search the web — while it answers you.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .            # text mode only
pip install -e ".[voice]"   # adds mic/speaker support (SpeechRecognition, PyAudio, pyttsx3)

cp .env.example .env
# then edit .env and set ANTHROPIC_API_KEY
```

`PyAudio` needs `portaudio` installed at the OS level first:

```bash
# macOS
brew install portaudio
# Debian/Ubuntu
sudo apt-get install portaudio19-dev
```

## Usage

Text mode (default, no microphone required):

```bash
jarvis
```

Voice mode (requires a microphone and the `voice` extra):

```bash
jarvis --voice
```

In voice mode, Jarvis listens for the wake word (default: "jarvis", set via
`JARVIS_WAKE_WORD`), then listens for your request, and speaks the reply back.
If no microphone is detected it automatically falls back to press-Enter-to-talk
so the rest of the pipeline still works.

Scripted one-off use:

```bash
jarvis --once "What's 12 times 7?"
```

## Configuration

All settings are read from environment variables (see `.env.example`):

| Variable               | Default            | Purpose                                   |
|-------------------------|--------------------|--------------------------------------------|
| `ANTHROPIC_API_KEY`     | *(required)*       | Your Claude API key                       |
| `JARVIS_MODEL`          | `claude-sonnet-5`  | Which Claude model to use                 |
| `JARVIS_NAME`           | `Jarvis`           | Assistant's name, used in prompts         |
| `JARVIS_WAKE_WORD`      | `jarvis`           | Wake word for voice mode                  |
| `JARVIS_VOICE`          | `false`            | Start in voice mode by default            |
| `OPENWEATHER_API_KEY`   | *(optional)*       | Enables the `get_weather` tool            |

## Architecture

```
src/jarvis/
  config.py       Settings loaded from the environment
  llm.py          Claude Messages API wrapper + tool-use loop
  assistant.py    Orchestrates conversation, speech I/O, and the tool-use loop
  main.py         CLI entry point
  tools/
    registry.py   Tool registration/dispatch shared with Claude's tool-use API
    builtin.py    time/date, calculator, notes, reminders, weather, web search
  speech/
    stt.py        Microphone -> text (SpeechRecognition)
    tts.py        Text -> speech (pyttsx3), falls back to printing
    wake_word.py  Wake-word gating, falls back to press-Enter-to-talk
```

Notes and reminders are persisted as JSON under `~/.jarvis/` (override with
`JARVIS_DATA_DIR`).

## Adding a new tool

Add a function to `src/jarvis/tools/builtin.py` (or a new module imported from
`tools/__init__.py`) decorated with the shared registry:

```python
@registry.register(
    name="my_tool",
    description="What this tool does, written for the model to read.",
    input_schema={
        "type": "object",
        "properties": {"arg": {"type": "string"}},
        "required": ["arg"],
    },
)
def my_tool(arg: str) -> str:
    return f"did something with {arg}"
```

It's automatically exposed to Claude and dispatched on the next tool call —
no other wiring required.

## Tests

```bash
pip install -e ".[dev]"
pytest
```

Tests mock the Anthropic client and the filesystem, so they run without an
API key, network access, or a microphone.
