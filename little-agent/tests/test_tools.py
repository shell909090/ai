"""Tests for tool manager and providers."""

import pytest

from little_agent.tools.exceptions import ToolExecutionError, ToolInvokeError
from little_agent.tools.manager import AggregatedToolManager
from tests.mocks import BuiltinToolProvider


@pytest.mark.asyncio
async def test_aggregated_manager_register_and_list() -> None:
    """Test register and list tools."""
    manager = AggregatedToolManager()
    provider = BuiltinToolProvider()
    manager.register(provider)
    tools = manager.list()
    assert "echo" in tools
    assert "add" in tools


@pytest.mark.asyncio
async def test_invoke_routes_to_provider() -> None:
    """Test invoke routes to correct provider."""
    manager = AggregatedToolManager()
    provider = BuiltinToolProvider()
    manager.register(provider)
    result = await manager.invoke("echo", text="hello")
    assert result == "hello"


@pytest.mark.asyncio
async def test_invoke_unknown_tool_raises() -> None:
    """Test invoke unknown tool raises ToolInvokeError."""
    manager = AggregatedToolManager()
    with pytest.raises(ToolInvokeError):
        await manager.invoke("nonexistent")


@pytest.mark.asyncio
async def test_builtin_echo() -> None:
    """Test builtin echo tool."""
    provider = BuiltinToolProvider()
    result = await provider.invoke("echo", text="world")
    assert result == "world"


@pytest.mark.asyncio
async def test_builtin_add() -> None:
    """Test builtin add tool."""
    provider = BuiltinToolProvider()
    result = await provider.invoke("add", a=1, b=2)
    assert result == 3


@pytest.mark.asyncio
async def test_builtin_add_invalid_type_raises() -> None:
    """Test builtin add with invalid types raises ToolExecutionError."""
    provider = BuiltinToolProvider()
    with pytest.raises(ToolExecutionError):
        await provider.invoke("add", a="x", b="y")


@pytest.mark.asyncio
async def test_builtin_unknown_tool_raises() -> None:
    """Test builtin unknown tool raises ToolExecutionError."""
    provider = BuiltinToolProvider()
    with pytest.raises(ToolExecutionError):
        await provider.invoke("nonexistent")
