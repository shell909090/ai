"""Built-in tool provider."""

from little_agent.types import JSONValue

from .exceptions import ToolExecutionError
from .protocol import ToolMap, ToolProvider


class BuiltinToolProvider(ToolProvider):
    """Provides built-in tools."""

    def __init__(self) -> None:
        self._tools: ToolMap = {
            "echo": (
                "Echo the input text back",
                [
                    ("text", "string", "The text to echo", True),
                ],
            ),
            "add": (
                "Add two numbers",
                [
                    ("a", "number", "First number", True),
                    ("b", "number", "Second number", True),
                ],
            ),
        }

    def list(self) -> ToolMap:
        """Return built-in tools."""
        return self._tools.copy()

    async def invoke(self, name: str, **kwargs: JSONValue) -> JSONValue:
        """Invoke a built-in tool."""
        if name == "echo":
            return kwargs.get("text", "")
        if name == "add":
            a = kwargs.get("a", 0)
            b = kwargs.get("b", 0)
            if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
                raise ToolExecutionError("Arguments must be numbers")
            return a + b
        raise ToolExecutionError(f"Unknown tool: {name}")
