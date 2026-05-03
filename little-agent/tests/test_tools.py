"""Tests for tool manager and providers."""

import pytest

from little_agent.backends.protocol import BackendToolCall, BackendTurnResult
from little_agent.tools.exceptions import ToolExecutionError, ToolInvokeError
from little_agent.tools.manager import ToolManager
from little_agent.tools.protocol import ToolMap, ToolProvider
from little_agent.types import JSONValue
from tests.mocks import BuiltinToolProvider, MockAgent, MockBackend, MockClient


class _FastPathProvider(ToolProvider):
    """Provider that exposes a named method for fast-path dispatch testing."""

    def __init__(self) -> None:
        self.invoke_called = False
        self.fast_called = False

    def list(self) -> ToolMap:
        return {
            "greet": ("Say hello", [("name", "string", "Name to greet", True)]),
            "invoke": ("A tool literally named invoke", []),
        }

    async def invoke(self, name: str, kwargs: dict[str, JSONValue]) -> JSONValue:
        self.invoke_called = True
        if name == "invoke":
            return "invoke-tool-result"
        return f"fallback:{name}"

    async def greet(self, **kwargs: JSONValue) -> JSONValue:
        self.fast_called = True
        return f"hello {kwargs.get('name', '')}"


@pytest.mark.asyncio
async def test_tool_manager_register_and_list() -> None:
    """Test register and list tools."""
    manager = ToolManager()
    provider = BuiltinToolProvider()
    manager.register(provider)
    tools = manager.list()
    assert "echo" in tools
    assert "add" in tools


@pytest.mark.asyncio
async def test_invoke_routes_to_provider() -> None:
    """Test invoke routes to correct provider."""
    manager = ToolManager()
    provider = BuiltinToolProvider()
    manager.register(provider)
    result = await manager.invoke("echo", {"text": "hello"})
    assert result == "hello"


@pytest.mark.asyncio
async def test_invoke_unknown_tool_raises() -> None:
    """Test invoke unknown tool raises ToolInvokeError."""
    manager = ToolManager()
    with pytest.raises(ToolInvokeError):
        await manager.invoke("nonexistent", {})


@pytest.mark.asyncio
async def test_builtin_echo() -> None:
    """Test builtin echo tool."""
    provider = BuiltinToolProvider()
    result = await provider.invoke("echo", {"text": "world"})
    assert result == "world"


@pytest.mark.asyncio
async def test_builtin_add() -> None:
    """Test builtin add tool."""
    provider = BuiltinToolProvider()
    result = await provider.invoke("add", {"a": 1, "b": 2})
    assert result == 3


@pytest.mark.asyncio
async def test_builtin_add_invalid_type_raises() -> None:
    """Test builtin add with invalid types raises ToolExecutionError."""
    provider = BuiltinToolProvider()
    with pytest.raises(ToolExecutionError):
        await provider.invoke("add", {"a": "x", "b": "y"})


@pytest.mark.asyncio
async def test_builtin_unknown_tool_raises() -> None:
    """Test builtin unknown tool raises ToolExecutionError."""
    provider = BuiltinToolProvider()
    with pytest.raises(ToolExecutionError):
        await provider.invoke("nonexistent", {})


@pytest.mark.asyncio
async def test_fast_path_dispatch_calls_method_directly() -> None:
    """Test that manager uses fast path when provider has a matching method."""
    manager = ToolManager()
    provider = _FastPathProvider()
    manager.register(provider)
    result = await manager.invoke("greet", {"name": "world"})
    assert result == "hello world"
    assert provider.fast_called is True
    assert provider.invoke_called is False


@pytest.mark.asyncio
async def test_fast_path_reserved_name_falls_back_to_invoke() -> None:
    """Test that a tool named 'invoke' is never fast-pathed."""
    manager = ToolManager()
    provider = _FastPathProvider()
    manager.register(provider)
    result = await manager.invoke("invoke", {})
    assert result == "invoke-tool-result"
    assert provider.invoke_called is True


@pytest.mark.asyncio
async def test_fast_path_absent_method_falls_back_to_invoke() -> None:
    """Test that manager falls back to provider.invoke() when no method exists."""
    manager = ToolManager()

    class _NoMethodProvider(ToolProvider):
        def list(self) -> ToolMap:
            return {"dynamo": ("dynamic tool", [])}

        async def invoke(self, name: str, kwargs: dict[str, JSONValue]) -> JSONValue:
            return f"fallback:{name}"

    provider = _NoMethodProvider()
    manager.register(provider)
    result = await manager.invoke("dynamo", {})
    assert result == "fallback:dynamo"


# ---------------------------------------------------------------------------
# T27: runtime dynamic tool subset selection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_allowed_tools_filters_tool_map() -> None:
    """When allowed_tools=["echo"], the session's turn tool map contains only echo."""
    captured: list[ToolMap] = []

    from collections.abc import AsyncIterator

    from little_agent.agent.core import SessionCore
    from little_agent.backends.protocol import Backend
    from little_agent.types import SessionUpdate

    class _CapturingBackend(Backend):
        """Backend that captures get_turn_tool_map() then returns a completed result."""

        def generate(self, session: object) -> AsyncIterator[SessionUpdate | BackendTurnResult]:
            return self._gen(session)

        async def _gen(self, session: object):  # type: ignore[override]
            if isinstance(session, SessionCore):
                captured.append(session.get_turn_tool_map())
            yield BackendTurnResult(
                output_text="ok",
                tool_calls=[],
                finish_reason="completed",
            )

    client = MockClient()
    provider = BuiltinToolProvider()
    # Bypass MockAgent's type hint; BuiltinToolProvider satisfies ToolProvider protocol.
    agent = MockAgent(backend=_CapturingBackend(), tools=provider, client=client)  # type: ignore[arg-type]
    session = await agent.new()

    await session.prompt("hello", allowed_tools=["echo"])

    assert len(captured) == 1, "Backend should have been called exactly once"
    turn_map = captured[0]
    assert "echo" in turn_map, "echo must appear in the filtered tool map"
    assert "add" not in turn_map, "add must be excluded by allowed_tools filter"


@pytest.mark.asyncio
async def test_disallowed_tool_call_results_in_failure() -> None:
    """A tool_call for a tool not in allowed_tools is recorded as failed without invocation."""
    client = MockClient()
    provider = BuiltinToolProvider()

    script = [
        BackendTurnResult(
            output_text="",
            tool_calls=[BackendToolCall(call_id="c1", tool_name="add", arguments={"a": 1, "b": 2})],
            finish_reason="tool_call",
        ),
        BackendTurnResult(
            output_text="done",
            tool_calls=[],
            finish_reason="completed",
        ),
    ]
    backend = MockBackend(script=script)
    agent = MockAgent(backend=backend, tools=provider, client=client)  # type: ignore[arg-type]
    session = await agent.new()

    await session.prompt("hello", allowed_tools=["echo"])

    # Find the tool_call_update for call_id "c1"
    updates = [
        u for u in client.updates if u.type == "tool_call_update" and u.data.get("call_id") == "c1"
    ]
    assert updates, "Expected a tool_call_update for call_id 'c1'"
    update = updates[0]
    assert update.data["status"] == "failed", (
        f"Expected status='failed', got {update.data['status']!r}"
    )
    content = update.data.get("content", "")
    assert "not in allowed list" in str(content) or "Permission denied" in str(content), (
        f"Expected 'not in allowed list' or 'Permission denied' in content, got {content!r}"
    )
    # The actual add(1, 2) = 3 result must NOT be the content (tool was not invoked)
    assert content != 3, (
        "add tool must not have been invoked (result 3 must not appear as tool output)"
    )


@pytest.mark.asyncio
async def test_allowed_tools_none_allows_all() -> None:
    """When allowed_tools=None (default), all registered tools are accessible."""
    client = MockClient()
    provider = BuiltinToolProvider()

    script = [
        BackendTurnResult(
            output_text="",
            tool_calls=[BackendToolCall(call_id="e1", tool_name="echo", arguments={"text": "hi"})],
            finish_reason="tool_call",
        ),
        BackendTurnResult(
            output_text="done",
            tool_calls=[],
            finish_reason="completed",
        ),
    ]
    backend = MockBackend(script=script)
    agent = MockAgent(backend=backend, tools=provider, client=client)  # type: ignore[arg-type]
    session = await agent.new()

    await session.prompt("hello")  # allowed_tools defaults to None

    updates = [
        u for u in client.updates if u.type == "tool_call_update" and u.data.get("call_id") == "e1"
    ]
    assert updates, "Expected a tool_call_update for call_id 'e1'"
    update = updates[0]
    assert update.data["status"] == "completed", (
        f"Expected status='completed', got {update.data['status']!r}"
    )
    assert update.data["content"] == "hi", (
        f"Expected echo to return 'hi', got {update.data['content']!r}"
    )
