from jarvis.assistant import Jarvis
from jarvis.config import JarvisConfig


def make_jarvis() -> Jarvis:
    config = JarvisConfig(anthropic_api_key="test-key", voice_enabled=False)
    return Jarvis(config)


def test_handle_message_appends_history_and_returns_reply(monkeypatch):
    jarvis = make_jarvis()

    def fake_respond(messages, protocol=None):
        updated = messages + [{"role": "assistant", "content": "hi there"}]
        return "hi there", updated

    monkeypatch.setattr(jarvis.brain, "respond", fake_respond)

    reply = jarvis.handle_message("hello")

    assert reply == "hi there"
    assert jarvis.messages[0] == {"role": "user", "content": "hello"}
    assert jarvis.messages[-1] == {"role": "assistant", "content": "hi there"}


def test_text_mode_has_no_speech_io():
    jarvis = make_jarvis()
    assert jarvis.stt is None
    assert jarvis.wake_word is None
    assert jarvis.tts.available is False
