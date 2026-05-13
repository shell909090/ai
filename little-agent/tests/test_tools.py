"""Tests for tool manager and providers."""

from unittest.mock import MagicMock

import pytest

from little_agent.agent.tool_manager import ToolManager
from little_agent.backends.protocol import BackendToolCall, BackendTurnResult
from little_agent.tools.protocol import ToolMap
from tests.mocks import BuiltinToolProvider, MockAgent, MockBackend, MockClient


@pytest.fixture
def mock_session() -> MagicMock:
    """Minimal session mock for direct tool dispatch calls."""
    s = MagicMock()
    s.id = "mock-session"
    return s


@pytest.mark.asyncio
async def test_tool_manager_register_and_list(mock_session: MagicMock) -> None:
    """Test register and desc_tool."""
    manager = ToolManager()
    provider = BuiltinToolProvider()
    manager.register(provider)
    tools = manager.desc_tool()
    assert "echo" in tools
    assert "add" in tools


@pytest.mark.asyncio
async def test_invoke_routes_to_provider(mock_session: MagicMock) -> None:
    """Test __getitem__ routes to correct provider callable."""
    manager = ToolManager()
    provider = BuiltinToolProvider()
    manager.register(provider)
    result = await manager["echo"]({"text": "hello"}, mock_session)
    assert result == "hello"


def test_invoke_unknown_tool_raises() -> None:
    """Test __getitem__ for unknown tool raises KeyError."""
    manager = ToolManager()
    with pytest.raises(KeyError):
        manager["nonexistent"]


@pytest.mark.asyncio
async def test_builtin_echo(mock_session: MagicMock) -> None:
    """Test builtin echo tool."""
    manager = ToolManager()
    manager.register(BuiltinToolProvider())
    result = await manager["echo"]({"text": "world"}, mock_session)
    assert result == "world"


@pytest.mark.asyncio
async def test_builtin_add(mock_session: MagicMock) -> None:
    """Test builtin add tool."""
    manager = ToolManager()
    manager.register(BuiltinToolProvider())
    result = await manager["add"]({"a": 1, "b": 2}, mock_session)
    assert result == 3


@pytest.mark.asyncio
async def test_builtin_add_invalid_type_raises(mock_session: MagicMock) -> None:
    """Test builtin add with invalid types raises TypeError."""
    manager = ToolManager()
    manager.register(BuiltinToolProvider())
    with pytest.raises(TypeError):
        await manager["add"]({"a": "x", "b": "y"}, mock_session)


def test_builtin_unknown_tool_raises() -> None:
    """Test KeyError for unknown tool name."""
    manager = ToolManager()
    manager.register(BuiltinToolProvider())
    with pytest.raises(KeyError):
        manager["nonexistent"]


@pytest.mark.asyncio
async def test_register_conflict_raises() -> None:
    """Registering the same tool name twice raises ValueError."""
    manager = ToolManager()
    manager.register(BuiltinToolProvider())
    with pytest.raises(ValueError):
        manager.register(BuiltinToolProvider())


# ---------------------------------------------------------------------------
# T44: desc_tool exclude parameter
# ---------------------------------------------------------------------------


def test_desc_tool_exclude_removes_named_tool() -> None:
    """desc_tool(exclude={"add"}) omits add from the result."""
    manager = ToolManager()
    manager.register(BuiltinToolProvider())
    result = manager.desc_tool(exclude={"add"})
    assert "echo" in result
    assert "add" not in result


def test_desc_tool_exclude_with_whitelist() -> None:
    """desc_tool(names, exclude) applies both filters."""
    manager = ToolManager()
    manager.register(BuiltinToolProvider())
    result = manager.desc_tool({"echo", "add"}, exclude={"add"})
    assert "echo" in result
    assert "add" not in result


def test_desc_tool_exclude_nonexistent_is_noop() -> None:
    """Excluding a name not in the registry has no effect."""
    manager = ToolManager()
    manager.register(BuiltinToolProvider())
    result = manager.desc_tool(exclude={"nonexistent"})
    assert "echo" in result
    assert "add" in result


def test_desc_tool_exclude_none_returns_all() -> None:
    """desc_tool(exclude=None) returns all tools unchanged."""
    manager = ToolManager()
    manager.register(BuiltinToolProvider())
    result = manager.desc_tool(exclude=None)
    assert "echo" in result
    assert "add" in result


# ---------------------------------------------------------------------------
# T27: runtime dynamic tool subset selection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_allowed_tools_filters_tool_map() -> None:
    """When allowed_tools=["echo"], the session's turn tool map contains only echo."""
    captured: list[ToolMap] = []

    from collections.abc import AsyncIterator

    from little_agent.agent.session import SessionCore
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
    agent = MockAgent(backend=_CapturingBackend(), tools=provider, client=client)
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
    agent = MockAgent(backend=backend, tools=provider, client=client)
    session = await agent.new()

    await session.prompt("hello", allowed_tools=["echo"])

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
    agent = MockAgent(backend=backend, tools=provider, client=client)
    session = await agent.new()

    await session.prompt("hello")

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
