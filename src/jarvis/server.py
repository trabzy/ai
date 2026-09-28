"""A small local web server that powers the Jarvis HUD.

Stdlib only: the browser gets a single-page app and talks to a JSON API.
Chat replies stream back as newline-delimited JSON events.
"""

from __future__ import annotations

import json
import threading
import traceback
import webbrowser
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from typing import Any

import anthropic

from .config import JarvisConfig
from .llm import ClaudeBrain
from .protocols import DEFAULT_PROTOCOL, protocol_catalog
from .tools import registry as tool_registry
from .tools import workspace

MAX_BODY_BYTES = 1_000_000
VENDOR_FILES = {"marked.min.js", "purify.min.js"}


@dataclass
class Session:
    messages: list[dict] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)


class JarvisApp:
    """State shared by all requests: the brain and per-browser conversations."""

    def __init__(self, config: JarvisConfig, brain: ClaudeBrain | None = None) -> None:
        self.config = config
        self.brain = brain or ClaudeBrain(config, tool_registry.specs(), tool_registry.execute)
        self._sessions: dict[str, Session] = {}
        self._sessions_lock = threading.Lock()

    def session(self, session_id: str) -> Session:
        with self._sessions_lock:
            return self._sessions.setdefault(session_id, Session())

    def reset(self, session_id: str) -> None:
        with self._sessions_lock:
            self._sessions.pop(session_id, None)

    def status(self) -> dict:
        return {
            "name": self.config.assistant_name,
            "model": self.config.model,
            "web_search": self.config.web_search,
            "protocols": protocol_catalog(),
            "default_protocol": DEFAULT_PROTOCOL,
            "tools": [spec["name"] for spec in self.brain.tool_specs],
        }

    def chat_events(self, session_id: str, message: str, protocol: str | None):
        """Yield UI events for one user turn, keeping history consistent on failure."""
        session = self.session(session_id)
        if not session.lock.acquire(blocking=False):
            yield {"type": "error", "text": "Still working on your previous request."}
            return
        try:
            checkpoint = len(session.messages)
            session.messages.append({"role": "user", "content": message})
            try:
                yield from self.brain.stream(session.messages, protocol)
            except Exception as exc:  # noqa: BLE001 - reported to the UI, history rolled back
                del session.messages[checkpoint:]
                yield {"type": "error", "text": _describe_error(exc)}
        finally:
            session.lock.release()


def _describe_error(exc: Exception) -> str:
    if isinstance(exc, anthropic.AuthenticationError):
        return "Authentication failed: check ANTHROPIC_API_KEY."
    if isinstance(exc, anthropic.RateLimitError):
        return "Rate limited by the API. Give it a moment and try again."
    if isinstance(exc, anthropic.APIStatusError):
        return f"API error {exc.status_code}: {exc.message}"
    if isinstance(exc, anthropic.APIConnectionError):
        return "Couldn't reach the Claude API. Check your network connection."
    traceback.print_exc()
    return f"Internal error: {exc}"


def _static(*parts: str) -> bytes:
    node = resources.files("jarvis.web")
    for part in parts:
        node = node.joinpath(part)
    return node.read_bytes()


def make_handler(app: JarvisApp) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "Jarvis/1.0"

        def log_message(self, format: str, *args: Any) -> None:  # quieter console
            if self.path.startswith("/api/chat"):
                super().log_message(format, *args)

        # -- helpers --------------------------------------------------------

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, payload: Any, status: int = 200) -> None:
            self._send(status, json.dumps(payload).encode(), "application/json")

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY_BYTES:
                raise ValueError("Request too large")
            raw = self.rfile.read(length) if length else b"{}"
            data = json.loads(raw or b"{}")
            if not isinstance(data, dict):
                raise ValueError("Expected a JSON object")
            return data

        # -- routes ---------------------------------------------------------

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path in {"/", "/index.html"}:
                self._send(200, _static("index.html"), "text/html; charset=utf-8")
            elif path.startswith("/vendor/") and path[len("/vendor/"):] in VENDOR_FILES:
                body = _static("vendor", path[len("/vendor/"):])
                self._send(200, body, "text/javascript; charset=utf-8")
            elif path == "/api/status":
                self._json(app.status())
            elif path == "/api/workspace":
                self._json(workspace.snapshot())
            else:
                self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:  # noqa: N802
            try:
                body = self._body()
            except (ValueError, json.JSONDecodeError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return

            path = self.path.split("?", 1)[0]
            if path == "/api/chat":
                self._chat(body)
            elif path == "/api/reset":
                app.reset(str(body.get("session", "")))
                self._json({"ok": True})
            elif path == "/api/task":
                self._toggle_task(body)
            else:
                self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

        def _toggle_task(self, body: dict) -> None:
            try:
                result = workspace.complete_task(
                    str(body["project"]), str(body["task_id"]), bool(body.get("done", True))
                )
            except (KeyError, ValueError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            self._json({"ok": True, "result": result})

        def _chat(self, body: dict) -> None:
            message = str(body.get("message", "")).strip()
            session_id = str(body.get("session", "")).strip()
            if not message or not session_id:
                self._json({"error": "message and session are required"}, HTTPStatus.BAD_REQUEST)
                return

            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()

            client_gone = False
            # Always drain the generator, even if the browser disconnects, so the
            # conversation history is never left with an unanswered tool call.
            for event in app.chat_events(session_id, message, body.get("protocol")):
                if client_gone:
                    continue
                try:
                    self.wfile.write((json.dumps(event) + "\n").encode())
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    client_gone = True

    return Handler


def serve(config: JarvisConfig, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    app = JarvisApp(config)
    httpd = ThreadingHTTPServer((host, port), make_handler(app))
    httpd.daemon_threads = True
    url = f"http://{'localhost' if host in {'127.0.0.1', '0.0.0.0'} else host}:{port}"
    print(f"{config.assistant_name} HUD online at {url}  (Ctrl+C to shut down)")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nPowering down.")
    finally:
        httpd.server_close()
