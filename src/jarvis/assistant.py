"""The Jarvis assistant: wires together the brain, tools, and speech I/O."""

from __future__ import annotations

from .config import JarvisConfig
from .llm import ClaudeBrain
from .speech.stt import SpeechToText
from .speech.tts import TextToSpeech
from .speech.wake_word import WakeWordListener
from .tools import registry as tool_registry

EXIT_WORDS = {"exit", "quit", "stop", "goodbye"}


class Jarvis:
    def __init__(self, config: JarvisConfig) -> None:
        self.config = config
        self.brain = ClaudeBrain(config, tool_registry.specs(), tool_registry.execute)
        self.messages: list[dict] = []
        self.protocol: str | None = None
        self.tts = TextToSpeech(enabled=config.voice_enabled)
        self.stt = SpeechToText() if config.voice_enabled else None
        self.wake_word = WakeWordListener(self.stt, config.wake_word) if self.stt else None

    def handle_message(self, text: str) -> str:
        self.messages.append({"role": "user", "content": text})
        reply, self.messages = self.brain.respond(self.messages, self.protocol)
        return reply

    def run_text_loop(self) -> None:
        print(f"{self.config.assistant_name} is online. Type 'exit' to quit.")
        while True:
            try:
                text = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not text:
                continue
            if text.lower() in EXIT_WORDS:
                break
            reply = self.handle_message(text)
            self.tts.speak(reply)

    def run_voice_loop(self) -> None:
        if self.stt is None or self.wake_word is None:
            raise RuntimeError("Voice mode is not enabled in the config.")
        print(f"{self.config.assistant_name} is online in voice mode.")
        while True:
            try:
                self.wake_word.wait_for_wake_word()
            except KeyboardInterrupt:
                break

            self.tts.speak("Yes?")
            try:
                text = self.stt.listen() if self.stt.available else input("You: ").strip()
            except (RuntimeError, KeyboardInterrupt) as exc:
                if isinstance(exc, KeyboardInterrupt):
                    break
                self.tts.speak(f"Sorry, I had trouble hearing you: {exc}")
                continue

            if not text:
                continue
            if text.lower().strip(".!?") in EXIT_WORDS:
                self.tts.speak("Goodbye.")
                break

            reply = self.handle_message(text)
            self.tts.speak(reply)
