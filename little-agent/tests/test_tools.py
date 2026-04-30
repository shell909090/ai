"""Tests for tool manager and providers."""

import pytest

from little_agent.tools.exceptions import ToolExecutionError, ToolInvokeError
from little_agent.tools.manager import ToolManager
from little_agent.tools.protocol import ToolMap, ToolProvider
from little_agent.types import JSONValue
from tests.mocks import BuiltinToolProvider


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
