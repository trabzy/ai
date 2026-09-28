from types import SimpleNamespace

from jarvis.config import JarvisConfig
from jarvis.llm import ClaudeBrain


def make_brain(responses, tool_executor=None):
    config = JarvisConfig(anthropic_api_key="test-key", model="test-model")
    tool_executor = tool_executor or (lambda name, args: "unused")
    brain = ClaudeBrain(config, tool_specs=[], tool_executor=tool_executor)

    responses_iter = iter(responses)

    class FakeMessages:
        def create(self, **kwargs):
            return next(responses_iter)

    brain.client = SimpleNamespace(messages=FakeMessages())
    return brain


def text_block(text):
    return SimpleNamespace(type="text", text=text)


def tool_use_block(name, arguments, block_id="tool_1"):
    return SimpleNamespace(type="tool_use", name=name, input=arguments, id=block_id)


def test_respond_returns_text_when_no_tool_use():
    response = SimpleNamespace(content=[text_block("Hello there.")], stop_reason="end_turn")
    brain = make_brain([response])

    reply, messages = brain.respond([{"role": "user", "content": "hi"}])

    assert reply == "Hello there."
    assert messages[-1]["role"] == "assistant"


def test_respond_executes_tool_and_continues():
    tool_response = SimpleNamespace(
        content=[tool_use_block("get_current_time", {})],
        stop_reason="tool_use",
    )
    final_response = SimpleNamespace(content=[text_block("It's 10 o'clock.")], stop_reason="end_turn")

    calls = []

    def tool_executor(name, args):
        calls.append((name, args))
        return "10:00:00"

    brain = make_brain([tool_response, final_response], tool_executor=tool_executor)
    reply, messages = brain.respond([{"role": "user", "content": "what time is it?"}])

    assert reply == "It's 10 o'clock."
    assert calls == [("get_current_time", {})]
    # A tool_result message should have been appended between the two model calls.
    tool_result_messages = [m for m in messages if m["role"] == "user" and isinstance(m["content"], list)]
    assert tool_result_messages[-1]["content"][0]["tool_use_id"] == "tool_1"
    assert tool_result_messages[-1]["content"][0]["content"] == "10:00:00"


def test_respond_gives_up_after_max_iterations():
    tool_response = SimpleNamespace(
        content=[tool_use_block("noop", {})],
        stop_reason="tool_use",
    )
    responses = [tool_response] * 8  # matches MAX_TOOL_ITERATIONS
    brain = make_brain(responses, tool_executor=lambda name, args: "ok")

    reply, _ = brain.respond([{"role": "user", "content": "loop forever"}])

    assert "stuck" in reply.lower()
