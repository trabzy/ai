"""Wake-word gating: waits until the user says the wake word before listening for a command.

Falls back to press-Enter-to-talk when no microphone is available, so the
assistant still runs (in a degraded mode) on machines without audio input.
"""

from __future__ import annotations

from .stt import SpeechToText


class WakeWordListener:
    def __init__(self, stt: SpeechToText, wake_word: str = "jarvis") -> None:
        self.stt = stt
        self.wake_word = wake_word.lower()

    def wait_for_wake_word(self) -> None:
        if not self.stt.available:
            input(f"[press Enter to talk to {self.wake_word.title()}] ")
            return
        print(f"Listening for the wake word '{self.wake_word}'...")
        while True:
            try:
                text = self.stt.listen(timeout=None, phrase_time_limit=3)
            except RuntimeError:
                input(f"[press Enter to talk to {self.wake_word.title()}] ")
                return
            if text and self.wake_word in text.lower():
                return
