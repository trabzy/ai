from types import SimpleNamespace

from jarvis.config import JarvisConfig
from jarvis.llm import FALLBACK_BETA, MAX_TOOL_ITERATIONS, WEB_SEARCH_TOOL, ClaudeBrain, _echo_content


class FakeStream:
    def __init__(self, response, events=None):
        self.response = response
        self.events = events if events is not None else [
            SimpleNamespace(type="text", text=b.text) for b in response.content if b.type == "text"
        ]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        return iter(self.events)

    def get_final_message(self):
        return self.response


def make_brain(responses, tool_executor=None, **config_overrides):
    config = JarvisConfig(anthropic_api_key="test-key", model="test-model", **config_overrides)
    tool_executor = tool_executor or (lambda name, args: "unused")
    brain = ClaudeBrain(config, tool_specs=[], tool_executor=tool_executor)

    responses_iter = iter(responses)
    calls = []

    class FakeMessages:
        def stream(self, **kwargs):
            calls.append(kwargs)
            item = next(responses_iter)
            return item if isinstance(item, FakeStream) else FakeStream(item)

    brain.client = SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages()))
    brain.calls = calls
    return brain


def text_block(text):
    return SimpleNamespace(type="text", text=text)


def tool_use_block(name, arguments, block_id="tool_1"):
    return SimpleNamespace(type="tool_use", name=name, input=arguments, id=block_id)


def message(content, stop_reason="end_turn"):
    usage = SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=0)
    return SimpleNamespace(content=content, stop_reason=stop_reason, usage=usage)


def test_respond_returns_text_when_no_tool_use():
    brain = make_brain([message([text_block("Hello there.")])])

    reply, messages = brain.respond([{"role": "user", "content": "hi"}])

    assert reply == "Hello there."
    assert messages[-1]["role"] == "assistant"


def test_respond_executes_tool_and_continues():
    calls = []

    def tool_executor(name, args):
        calls.append((name, args))
        return "10:00:00"

    brain = make_brain(
        [
            message([tool_use_block("get_current_time", {})], stop_reason="tool_use"),
            message([text_block("It's 10 o'clock.")]),
        ],
        tool_executor=tool_executor,
    )
    reply, messages = brain.respond([{"role": "user", "content": "what time is it?"}])

    assert reply == "It's 10 o'clock."
    assert calls == [("get_current_time", {})]
    tool_result_messages = [m for m in messages if m["role"] == "user" and isinstance(m["content"], list)]
    assert tool_result_messages[-1]["content"][0]["tool_use_id"] == "tool_1"
    assert tool_result_messages[-1]["content"][0]["content"] == "10:00:00"


def test_tool_errors_are_flagged():
    brain = make_brain(
        [
            message([tool_use_block("broken", {})], stop_reason="tool_use"),
            message([text_block("That failed.")]),
        ],
        tool_executor=lambda name, args: "Error running tool 'broken': boom",
    )
    messages = [{"role": "user", "content": "go"}]
    events = list(brain.stream(messages))

    assert messages[2]["content"][0]["is_error"] is True
    tool_events = [e for e in events if e["type"] == "tool"]
    assert tool_events[-1]["status"] == "error"


def test_stream_emits_text_usage_and_done_events():
    brain = make_brain([message([text_block("Hi.")])])
    events = list(brain.stream([{"role": "user", "content": "hi"}]))

    types = [e["type"] for e in events]
    assert types == ["text", "usage", "done"]
    assert events[-1]["text"] == "Hi."


def test_respond_gives_up_after_max_iterations():
    loop = message([tool_use_block("noop", {})], stop_reason="tool_use")
    brain = make_brain([loop] * MAX_TOOL_ITERATIONS, tool_executor=lambda name, args: "ok")

    reply, _ = brain.respond([{"role": "user", "content": "loop forever"}])

    assert "stuck" in reply.lower()


def test_refusal_is_not_kept_in_history():
    brain = make_brain([message([], stop_reason="refusal")])
    messages = [{"role": "user", "content": "something"}]
    events = list(brain.stream(messages))

    assert len(messages) == 1
    assert any(e["type"] == "notice" for e in events)
    assert events[-1]["type"] == "done"


def test_pause_turn_resumes_without_tool_results():
    brain = make_brain(
        [message([text_block("Searching")], stop_reason="pause_turn"), message([text_block(" done.")])]
    )
    messages = [{"role": "user", "content": "search"}]
    reply_events = list(brain.stream(messages))

    assert [m["role"] for m in messages] == ["user", "assistant", "assistant"]
    assert reply_events[-1]["text"] == "Searching done."


def test_request_includes_protocol_effort_web_search_and_fallbacks():
    brain = make_brain([message([text_block("ok")])])
    list(brain.stream([{"role": "user", "content": "hi"}], protocol="strategist"))

    kwargs = brain.calls[0]
    assert kwargs["output_config"] == {"effort": "high"}
    assert WEB_SEARCH_TOOL in kwargs["tools"]
    assert kwargs["betas"] == [FALLBACK_BETA]
    assert kwargs["fallbacks"] == "default"
    assert "Strategist protocol" in kwargs["system"][1]["text"]
    assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_optional_request_features_can_be_disabled():
    brain = make_brain([message([text_block("ok")])], effort=None, web_search=False, fallbacks=False)
    list(brain.stream([{"role": "user", "content": "hi"}]))

    kwargs = brain.calls[0]
    assert "output_config" not in kwargs
    assert "betas" not in kwargs and "fallbacks" not in kwargs
    assert WEB_SEARCH_TOOL not in kwargs["tools"]


def test_web_search_events_are_surfaced():
    server_use = SimpleNamespace(type="server_tool_use", id="srv_1", name="web_search", input={"query": "jarvis"})
    result = SimpleNamespace(
        type="web_search_tool_result",
        tool_use_id="srv_1",
        content=[SimpleNamespace(title="Jarvis", url="https://example.com")],
    )
    events = [
        SimpleNamespace(type="content_block_start", content_block=server_use),
        SimpleNamespace(type="content_block_stop", content_block=server_use),
        SimpleNamespace(type="content_block_stop", content_block=result),
        SimpleNamespace(type="text", text="Found it."),
    ]
    brain = make_brain([FakeStream(message([text_block("Found it.")]), events)])
    out = list(brain.stream([{"role": "user", "content": "search"}]))

    tool_events = [e for e in out if e["type"] == "tool"]
    assert tool_events[0]["status"] == "running"
    assert tool_events[-1]["status"] == "done"
    assert tool_events[-1]["sources"] == [{"title": "Jarvis", "url": "https://example.com"}]


def test_echo_content_drops_pre_fallback_internal_blocks():
    content = [
        {"type": "thinking", "thinking": "", "signature": "x"},
        {"type": "text", "text": "partial"},
        {"type": "tool_use", "id": "t1", "name": "x", "input": {}},
        {"type": "fallback", "from": {"model": "a"}, "to": {"model": "b"}},
        {"type": "text", "text": "rest"},
    ]
    assert _echo_content(content) == [
        {"type": "text", "text": "partial"},
        {"type": "text", "text": "rest"},
    ]
