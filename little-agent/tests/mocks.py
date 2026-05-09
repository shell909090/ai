"""Mock implementations for testing."""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator, Iterator
from typing import Any

from little_agent.agent.core import AgentCore
from little_agent.agent.protocol import Session
from little_agent.backends.protocol import Backend, BackendTurnResult
from little_agent.frontends.protocol import Client
from little_agent.tools.exceptions import ToolExecutionError
from little_agent.tools.manager import ToolManager
from little_agent.tools.protocol import AsyncToolFn, ToolArgDef, ToolDef, ToolProvider
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


class MockToolProvider:
    """Mock tool provider with preset responses."""

    def __init__(
        self,
        tools: dict[str, ToolDef] | None = None,
        responses: dict[str, JSONValue] | None = None,
        errors: set[str] | None = None,
    ) -> None:
        self._tools: dict[str, ToolDef] = tools or {}
        self._responses = responses or {}
        self._errors = errors or set()

    def __iter__(self) -> Iterator[tuple[str, ToolDef, AsyncToolFn]]:
        """Yield (name, tooldef, fn) triples."""
        for name, tooldef in self._tools.items():

            async def _fn(args: dict[str, JSONValue], _name: str = name) -> JSONValue:
                if _name in self._errors:
                    raise ValueError(f"Tool {_name} failed")
                if _name in self._responses:
                    return self._responses[_name]
                return {"result": "ok"}

            yield name, tooldef, _fn


class BuiltinToolProvider:
    """Provides built-in tools for testing."""

    def __iter__(self) -> Iterator[tuple[str, ToolDef, AsyncToolFn]]:
        """Yield (name, tooldef, fn) triples for echo and add."""
        yield (
            "echo",
            ToolDef(
                desc="Echo the input text back",
                args=[
                    ToolArgDef(name="text", type="string", desc="The text to echo", required=True)
                ],
            ),
            self._echo,
        )
        yield (
            "add",
            ToolDef(
                desc="Add two numbers",
                args=[
                    ToolArgDef(name="a", type="number", desc="First number", required=True),
                    ToolArgDef(name="b", type="number", desc="Second number", required=True),
                ],
            ),
            self._add,
        )

    async def _echo(self, args: dict[str, JSONValue]) -> JSONValue:
        return args.get("text", "")

    async def _add(self, args: dict[str, JSONValue]) -> JSONValue:
        a = args.get("a", 0)
        b = args.get("b", 0)
        if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
            raise ToolExecutionError("Arguments must be numbers")
        return a + b


class MockAgent:
    """Mock agent for frontend and tools integration testing."""

    def __init__(
        self,
        backend: MockBackend | None = None,
        tools: ToolProvider | None = None,
        client: MockClient | None = None,
        permissions: Any = None,
    ) -> None:
        self._backend = backend or MockBackend()
        self._client = client or MockClient()
        tool_provider = tools if tools is not None else MockToolProvider()
        tool_mgr = ToolManager()
        tool_mgr.register(tool_provider)
        self.tools: ToolManager = tool_mgr
        self._agent = AgentCore(
            client=self._client,
            backend=self._backend,
            tools=tool_mgr,
            permissions=permissions,
        )

    async def new(self, cwd: str | None = None) -> Session:
        """Create a new mock session."""
        return await self._agent.new(cwd=cwd)

    async def load(self, data: JSONValue) -> Session:
        """Load a mock session."""
        return await self._agent.load(data)
