from jarvis.tools.registry import ToolRegistry


def make_registry() -> ToolRegistry:
    registry = ToolRegistry()

    @registry.register(
        name="add",
        description="Add two numbers.",
        input_schema={
            "type": "object",
            "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
            "required": ["a", "b"],
        },
    )
    def add(a: float, b: float) -> float:
        return a + b

    return registry


def test_specs_shape():
    registry = make_registry()
    specs = registry.specs()
    assert specs == [
        {
            "name": "add",
            "description": "Add two numbers.",
            "input_schema": {
                "type": "object",
                "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                "required": ["a", "b"],
            },
        }
    ]


def test_execute_calls_handler():
    registry = make_registry()
    assert registry.execute("add", {"a": 2, "b": 3}) == "5"


def test_execute_unknown_tool():
    registry = make_registry()
    result = registry.execute("subtract", {})
    assert "unknown tool" in result.lower()


def test_execute_handles_handler_exception():
    registry = make_registry()
    result = registry.execute("add", {"a": 1})  # missing required arg 'b'
    assert "error running tool" in result.lower()
