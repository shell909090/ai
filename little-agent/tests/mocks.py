"""Mock implementations for testing."""

from __future__ import annotations

from little_agent.agent.core import AgentCore
from little_agent.backends.protocol import Backend, BackendTurnResult
from little_agent.frontends.protocol import Client, SessionUpdate
from little_agent.tools.protocol import ToolManager, ToolMap
from little_agent.types import JSONValue


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

    async def generate(self, session: object) -> BackendTurnResult:
        """Return next scripted result."""
        self.sessions.append(session)
        if self._index < len(self._script):
            result = self._script[self._index]
            self._index += 1
            return result
        return BackendTurnResult(
            output_text="default",
            tool_calls=[],
            finish_reason="completed",
        )


class MockToolManager(ToolManager):
    """Mock tool manager with preset responses."""

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

    async def invoke(self, name: str, **kwargs: JSONValue) -> JSONValue:
        """Return preset response or error."""
        if name in self._errors:
            raise ValueError(f"Tool {name} failed")
        if name in self._responses:
            return self._responses[name]
        return {"result": "ok"}


class MockAgent:
    """Mock agent for frontend and tools integration testing."""

    def __init__(
        self,
        backend: MockBackend | None = None,
        tools: MockToolManager | None = None,
        client: MockClient | None = None,
    ) -> None:
        self._backend = backend or MockBackend()
        self._tools = tools or MockToolManager()
        self._client = client or MockClient()
        self._agent = AgentCore(
            client=self._client,
            backend=self._backend,
            tools=self._tools,
        )

    async def new(self, cwd: str | None = None) -> object:
        """Create a new mock session."""
        return await self._agent.new(cwd=cwd)

    async def load(self, data: JSONValue) -> object:
        """Load a mock session."""
        return await self._agent.load(data)
