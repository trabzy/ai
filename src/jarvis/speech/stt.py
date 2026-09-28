"""Speech-to-text input via a microphone, using SpeechRecognition + Google's API."""

from __future__ import annotations


class SpeechToText:
    def __init__(self) -> None:
        self._sr = None
        self._recognizer = None
        self._mic = None
        try:
            import speech_recognition as sr

            self._sr = sr
            self._recognizer = sr.Recognizer()
            self._mic = sr.Microphone()
        except Exception:
            # No SpeechRecognition/PyAudio installed, or no microphone attached.
            pass

    @property
    def available(self) -> bool:
        return self._recognizer is not None and self._mic is not None

    def listen(self, timeout: float | None = 5, phrase_time_limit: float | None = 10) -> str | None:
        """Listen for one utterance and transcribe it. Returns None if nothing was understood."""
        if not self.available:
            raise RuntimeError(
                "Speech recognition is unavailable. Install the 'voice' extra "
                "(pip install '.[voice]') and connect a microphone."
            )
        with self._mic as source:
            self._recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio = self._recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
        try:
            return self._recognizer.recognize_google(audio)
        except self._sr.UnknownValueError:
            return None
        except self._sr.RequestError as exc:
            raise RuntimeError(f"Speech recognition service error: {exc}") from exc
