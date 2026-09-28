import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from jarvis.config import JarvisConfig
from jarvis.server import JarvisApp, make_handler
from jarvis.tools import builtin


class FakeBrain:
    tool_specs = [{"name": "demo"}]

    def __init__(self, fail=False):
        self.fail = fail

    def stream(self, messages, protocol=None):
        yield {"type": "text", "text": f"[{protocol}] ok"}
        if self.fail:
            raise RuntimeError("boom")
        messages.append({"role": "assistant", "content": "ok"})
        yield {"type": "done", "text": "ok"}


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(builtin, "DATA_DIR", tmp_path)


def make_app(**kw):
    return JarvisApp(JarvisConfig(anthropic_api_key="k"), brain=FakeBrain(**kw))


def test_chat_events_keep_history():
    app = make_app()
    events = list(app.chat_events("s1", "hello", "solver"))
    assert events[0] == {"type": "text", "text": "[solver] ok"}
    assert [m["role"] for m in app.session("s1").messages] == ["user", "assistant"]


def test_chat_events_roll_back_history_on_error():
    app = make_app(fail=True)
    events = list(app.chat_events("s1", "hello", None))
    assert events[-1]["type"] == "error"
    assert app.session("s1").messages == []
    assert not app.session("s1").lock.locked()


@pytest.fixture
def server():
    app = make_app()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def _post(url, payload):
    req = urllib.request.Request(url, json.dumps(payload).encode(), {"Content-Type": "application/json"})
    return urllib.request.urlopen(req)


def test_http_routes(server):
    html = urllib.request.urlopen(server + "/").read().decode()
    assert "J.A.R.V.I.S." in html

    assert b"marked" in urllib.request.urlopen(server + "/vendor/marked.min.js").read(200)

    status = json.load(urllib.request.urlopen(server + "/api/status"))
    assert any(p["key"] == "strategist" for p in status["protocols"])

    lines = _post(server + "/api/chat", {"session": "a", "message": "hi", "protocol": "ideas"}).read().decode()
    events = [json.loads(line) for line in lines.splitlines()]
    assert events[-1]["type"] == "done"

    assert json.load(urllib.request.urlopen(server + "/api/workspace")) == {"projects": []}
