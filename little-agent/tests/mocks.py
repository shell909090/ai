"""Mock implementations for testing."""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any

from little_agent.agent.core import AgentCore
from little_agent.agent.protocol import Session
from little_agent.backends.protocol import Backend, BackendTurnResult
from little_agent.frontends.protocol import Client
from little_agent.tools.exceptions import ToolExecutionError
from little_agent.tools.protocol import ToolMap, ToolProvider
from little_agent.types import JSONValue, SessionUpdate


class MockClient(Client):
    """Mock client that collects session updates."""

    def __init__(self) -> None:
        self.updates: list[SessionUpdate] = []

    async def update(self, session: object, update: SessionUpdate) -> None:
        """Collect update."""
        self.updates.append(update)

    async def request_permission(
        self,
        session: object,
        kind: str,
        payload: dict[str, JSONValue],
    ) -> bool:
        """Always grant permission."""
        return True


class MockBackend(Backend):
    """Mock backend that returns scripted results."""

    def __init__(self, script: list[BackendTurnResult] | None = None) -> None:
        self._script = script or []
        self._index = 0
        self.sessions: list[object] = []

    def set_script(self, script: list[BackendTurnResult]) -> None:
        """Set a new script."""
        self._script = script
        self._index = 0

    def generate(self, session: object) -> AsyncIterator[SessionUpdate | BackendTurnResult]:
        """Return async iterator for scripted results."""
        return self._gen(session)

    async def _gen(
        self, session: object
    ) -> AsyncGenerator[SessionUpdate | BackendTurnResult, None]:
        """Async generator yielding the next scripted BackendTurnResult.

        Mirrors real backend streaming: thinking_text is emitted as a
        thinking_chunk update before the final BackendTurnResult.
        """
        self.sessions.append(session)
        if self._index < len(self._script):
            result = self._script[self._index]
            self._index += 1
            if result.thinking_text:
                yield SessionUpdate(type="thinking_chunk", data={"text": result.thinking_text})
            yield result
        else:
            yield BackendTurnResult(
                output_text="default",
                tool_calls=[],
                finish_reason="completed",
            )


class MockToolProvider(ToolProvider):
    """Mock tool provider with preset responses."""

    def __init__(
        self,
        tools: ToolMap | None = None,
        responses: dict[str, JSONValue] | None = None,
        errors: set[str] | None = None,
    ) -> None:
        self._tools = tools or {}
        self._responses = responses or {}
        self._errors = errors or set()

    def list(self) -> ToolMap:
        """Return tool map."""
        return self._tools.copy()

    async def invoke(self, name: str, kwargs: dict[str, JSONValue]) -> JSONValue:
        """Return preset response or error."""
        if name in self._errors:
            raise ValueError(f"Tool {name} failed")
        if name in self._responses:
            return self._responses[name]
        return {"result": "ok"}


class BuiltinToolProvider(ToolProvider):
    """Provides built-in tools for testing."""

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

    async def invoke(self, name: str, kwargs: dict[str, JSONValue]) -> JSONValue:
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


class MockAgent:
    """Mock agent for frontend and tools integration testing."""

    def __init__(
        self,
        backend: MockBackend | None = None,
        tools: MockToolProvider | None = None,
        client: MockClient | None = None,
        permissions: Any = None,
    ) -> None:
        self._backend = backend or MockBackend()
        self._tools = tools or MockToolProvider()
        self._client = client or MockClient()
        self.tools: ToolProvider = self._tools
        self._agent = AgentCore(
            client=self._client,
            backend=self._backend,
            tools=self._tools,
            permissions=permissions,
        )

    async def new(self, cwd: str | None = None) -> Session:
        """Create a new mock session."""
        return await self._agent.new(cwd=cwd)

    async def load(self, data: JSONValue) -> Session:
        """Load a mock session."""
        return await self._agent.load(data)
