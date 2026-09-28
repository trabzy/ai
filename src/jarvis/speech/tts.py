"""Text-to-speech output. Falls back to printing if no TTS engine is available."""

from __future__ import annotations


class TextToSpeech:
    def __init__(self, enabled: bool = True, rate: int = 180) -> None:
        self.enabled = enabled
        self._engine = None
        if enabled:
            try:
                import pyttsx3

                self._engine = pyttsx3.init()
                self._engine.setProperty("rate", rate)
            except Exception:
                self._engine = None

    @property
    def available(self) -> bool:
        return self._engine is not None

    def speak(self, text: str) -> None:
        print(f"Jarvis: {text}")
        if self._engine is None:
            return
        try:
            self._engine.say(text)
            self._engine.runAndWait()
        except Exception:
            pass
