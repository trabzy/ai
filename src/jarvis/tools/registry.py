"""A small registry that maps Claude tool-use calls to Python functions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    handler: Callable[..., Any]


class ToolRegistry:
    """Holds tool definitions and dispatches tool-use calls to their handlers."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, name: str, description: str, input_schema: dict) -> Callable:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._tools[name] = Tool(name, description, input_schema, func)
            return func

        return decorator

    def specs(self) -> list[dict]:
        """Tool definitions in the shape Claude's Messages API expects."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in self._tools.values()
        ]

    def execute(self, name: str, arguments: dict) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return f"Error: unknown tool '{name}'"
        try:
            result = tool.handler(**arguments)
        except Exception as exc:  # noqa: BLE001 - surfaced to the model as a tool result
            return f"Error running tool '{name}': {exc}"
        return str(result)
