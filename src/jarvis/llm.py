"""Wraps the Claude Messages API: streaming, the tool-use loop, and server tools."""

from __future__ import annotations

import datetime
from typing import Any, Callable, Iterator

import anthropic

from .config import JarvisConfig
from .protocols import Protocol, get_protocol

MAX_TOOL_ITERATIONS = 12
MAX_TOKENS = 64000
FALLBACK_BETA = "server-side-fallback-2026-07-01"
WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search", "max_uses": 5}

# Block types that must not be echoed back when they precede a mid-output fallback.
_PRE_FALLBACK_DROP = {"thinking", "redacted_thinking", "tool_use"}

Event = dict[str, Any]


def _block_to_param(block: Any) -> dict:
    """Convert an SDK content block (or a test double) into a request param dict."""
    if isinstance(block, dict):
        return block
    if hasattr(block, "to_dict"):
        return block.to_dict()
    return {k: v for k, v in vars(block).items() if not k.startswith("_")}


def _echo_content(content: list[Any]) -> list[dict]:
    """Prepare an assistant turn for replay, following the fallback echo rules."""
    blocks = [_block_to_param(b) for b in content]
    boundary = max((i for i, b in enumerate(blocks) if b.get("type") == "fallback"), default=-1)
    if boundary < 0:
        return blocks

    result_ids = {
        b.get("tool_use_id") for b in blocks if b.get("type", "").endswith("_tool_result")
    }
    kept = []
    for i, block in enumerate(blocks):
        kind = block.get("type")
        if i < boundary:
            if kind in _PRE_FALLBACK_DROP:
                continue
            if kind == "server_tool_use" and block.get("id") not in result_ids:
                continue
        if kind == "fallback":
            continue
        kept.append(block)
    return kept


def _truncate(text: str, limit: int = 600) -> str:
    return text if len(text) <= limit else text[:limit] + "…"


class ClaudeBrain:
    """Streams conversation turns to Claude and resolves any tool calls it makes."""

    def __init__(
        self,
        config: JarvisConfig,
        tool_specs: list[dict],
        tool_executor: Callable[[str, dict], str],
    ) -> None:
        self.client = anthropic.Anthropic(api_key=config.anthropic_api_key)
        self.config = config
        self.model = config.model
        self.system_prompt = config.system_prompt
        self.tool_specs = list(tool_specs)
        if config.web_search:
            self.tool_specs.append(WEB_SEARCH_TOOL)
        self.tool_executor = tool_executor

    # ------------------------------------------------------------------
    # Request construction
    # ------------------------------------------------------------------

    def _request_kwargs(self, messages: list[dict], protocol: Protocol) -> dict:
        today = datetime.date.today().strftime("%A %d %B %Y")
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": MAX_TOKENS,
            "system": [
                # Stable prefix first so it caches; volatile bits go after it.
                {"type": "text", "text": self.system_prompt, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": f"Today is {today}.\n\n{protocol.instructions}"},
            ],
            "tools": self.tool_specs,
            "messages": messages,
        }
        if self.config.effort:
            kwargs["output_config"] = {"effort": protocol.effort or self.config.effort}
        if self.config.fallbacks:
            kwargs["betas"] = [FALLBACK_BETA]
            kwargs["fallbacks"] = "default"
        return kwargs

    # ------------------------------------------------------------------
    # Streaming loop
    # ------------------------------------------------------------------

    def stream(self, messages: list[dict], protocol: str | None = None) -> Iterator[Event]:
        """Run the conversation forward, yielding UI events as they happen.

        ``messages`` is extended in place with every assistant turn and tool
        result, so the caller's history stays valid for the next request.
        The final event is always ``{"type": "done", "text": <full reply>}``.
        """
        proto = get_protocol(protocol)
        reply_parts: list[str] = []

        for _ in range(MAX_TOOL_ITERATIONS):
            response = None
            with self.client.beta.messages.stream(**self._request_kwargs(messages, proto)) as stream:
                for event in stream:
                    yield from self._translate_event(event, reply_parts)
                response = stream.get_final_message()

            usage = getattr(response, "usage", None)
            if usage is not None:
                yield {
                    "type": "usage",
                    "input_tokens": getattr(usage, "input_tokens", 0) or 0,
                    "output_tokens": getattr(usage, "output_tokens", 0) or 0,
                    "cache_read_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
                }

            stop_reason = response.stop_reason
            if stop_reason == "refusal":
                # Don't keep the declined turn in history; the user can rephrase.
                yield {"type": "notice", "level": "warn", "text": "Request declined by safety systems."}
                text = "".join(reply_parts).strip() or "I'm afraid I can't help with that one, sir."
                yield {"type": "done", "text": text}
                return

            messages.append({"role": "assistant", "content": _echo_content(response.content)})

            if stop_reason == "pause_turn":
                continue

            tool_uses = [b for b in response.content if getattr(b, "type", None) == "tool_use"]
            if stop_reason == "max_tokens":
                if tool_uses:
                    messages.pop()  # an unanswered, possibly truncated tool call
                yield {"type": "notice", "level": "warn", "text": "Reply hit the length limit."}
                break
            if stop_reason != "tool_use" or not tool_uses:
                break

            results = []
            for block in tool_uses:
                output = self.tool_executor(block.name, block.input or {})
                is_error = output.startswith("Error")
                yield {
                    "type": "tool",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input or {},
                    "status": "error" if is_error else "done",
                    "output": _truncate(output),
                }
                result = {"type": "tool_result", "tool_use_id": block.id, "content": output}
                if is_error:
                    result["is_error"] = True
                results.append(result)
            # All results for one turn go back in a single user message.
            messages.append({"role": "user", "content": results})
            reply_parts.append("\n\n")
        else:
            yield {"type": "notice", "level": "warn", "text": "Stopped after too many tool steps."}
            reply_parts.append("\n\nI got stuck working through that, sorry.")

        text = "".join(reply_parts).strip() or "I don't have a reply for that."
        yield {"type": "done", "text": text}

    def _translate_event(self, event: Any, reply_parts: list[str]) -> Iterator[Event]:
        kind = getattr(event, "type", None)
        if kind == "text":
            reply_parts.append(event.text)
            yield {"type": "text", "text": event.text}
        elif kind == "content_block_start":
            block = event.content_block
            btype = getattr(block, "type", None)
            if btype in {"tool_use", "server_tool_use"}:
                yield {"type": "tool", "id": block.id, "name": block.name, "status": "running"}
            elif btype == "thinking":
                yield {"type": "thinking"}
            elif btype == "fallback":
                yield {"type": "notice", "level": "info", "text": "Switched to a fallback model."}
        elif kind == "content_block_stop":
            block = getattr(event, "content_block", None)
            btype = getattr(block, "type", None)
            if btype == "server_tool_use":
                yield {
                    "type": "tool",
                    "id": block.id,
                    "name": block.name,
                    "input": getattr(block, "input", None) or {},
                    "status": "running",
                }
            elif btype == "web_search_tool_result":
                yield self._search_result_event(block)

    @staticmethod
    def _search_result_event(block: Any) -> Event:
        content = getattr(block, "content", None)
        if not isinstance(content, list):  # error results are an object, not a list
            code = getattr(content, "error_code", "unknown error")
            return {"type": "tool", "id": block.tool_use_id, "name": "web_search",
                    "status": "error", "output": f"Search failed: {code}"}
        sources = [
            {"title": getattr(r, "title", "") or getattr(r, "url", ""), "url": getattr(r, "url", "")}
            for r in content
        ]
        return {"type": "tool", "id": block.tool_use_id, "name": "web_search", "status": "done",
                "output": f"{len(sources)} results", "sources": sources[:6]}

    # ------------------------------------------------------------------
    # Blocking convenience wrapper (CLI / scripting)
    # ------------------------------------------------------------------

    def respond(self, messages: list[dict], protocol: str | None = None) -> tuple[str, list[dict]]:
        """Run the conversation to completion and return (reply, updated history)."""
        messages = list(messages)
        text = ""
        for event in self.stream(messages, protocol):
            if event["type"] == "done":
                text = event["text"]
        return text, messages
