"""Wraps the Claude Messages API and drives the tool-use loop."""

from __future__ import annotations

from typing import Any, Callable

import anthropic

from .config import JarvisConfig

MAX_TOOL_ITERATIONS = 8
MAX_TOKENS = 1024


class ClaudeBrain:
    """Sends conversation turns to Claude and resolves any tool calls it makes."""

    def __init__(
        self,
        config: JarvisConfig,
        tool_specs: list[dict],
        tool_executor: Callable[[str, dict], str],
    ) -> None:
        self.client = anthropic.Anthropic(api_key=config.anthropic_api_key)
        self.model = config.model
        self.system_prompt = config.system_prompt
        self.tool_specs = tool_specs
        self.tool_executor = tool_executor

    def respond(self, messages: list[dict]) -> tuple[str, list[dict]]:
        """Run the conversation forward until Claude gives a final text reply.

        Returns the reply text and the updated message history (including any
        assistant tool-use turns and tool results), so the caller can persist it.
        """
        messages = list(messages)

        for _ in range(MAX_TOOL_ITERATIONS):
            response = self.client.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=self.system_prompt,
                tools=self.tool_specs,
                messages=messages,
            )
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                return self._extract_text(response), messages

            tool_results = self._run_tools(response.content)
            messages.append({"role": "user", "content": tool_results})

        return "I got stuck working through that, sorry.", messages

    def _run_tools(self, content: list[Any]) -> list[dict]:
        results = []
        for block in content:
            if getattr(block, "type", None) != "tool_use":
                continue
            output = self.tool_executor(block.name, block.input)
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output,
                }
            )
        return results

    @staticmethod
    def _extract_text(response: Any) -> str:
        parts = [block.text for block in response.content if getattr(block, "type", None) == "text"]
        text = "\n".join(parts).strip()
        return text or "I don't have a reply for that."
