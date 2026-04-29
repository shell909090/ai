"""Tests for bash tool provider."""

import pytest

from little_agent.tools.bash import BashToolProvider


@pytest.mark.asyncio
async def test_bash_list() -> None:
    """Test BashToolProvider lists bash tool."""
    provider = BashToolProvider()
    tools = provider.list()
    assert "bash" in tools
    assert "command" in str(tools)


@pytest.mark.asyncio
async def test_bash_echo() -> None:
    """Test bash tool executes echo command."""
    provider = BashToolProvider()
    result = await provider.invoke("bash", command="echo hello")
    assert isinstance(result, str)
    assert "hello" in result


@pytest.mark.asyncio
async def test_bash_stderr_included() -> None:
    """Test bash tool includes stderr in output."""
    provider = BashToolProvider()
    result = await provider.invoke("bash", command="echo error >&2")
    assert isinstance(result, str)
    assert "error" in result


@pytest.mark.asyncio
async def test_bash_invalid_command_type_raises() -> None:
    """Test bash tool with non-string command raises ValueError."""
    provider = BashToolProvider()
    with pytest.raises(ValueError, match="command must be a string"):
        await provider.invoke("bash", command=123)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_bash_unknown_tool_raises() -> None:
    """Test invoking unknown tool raises ValueError."""
    provider = BashToolProvider()
    with pytest.raises(ValueError, match="Unknown tool"):
        await provider.invoke("nonexistent")


@pytest.mark.asyncio
async def test_bash_timeout() -> None:
    """Test bash tool times out on long-running command."""
    provider = BashToolProvider()
    result = await provider.invoke("bash", command="sleep 60")
    assert "timed out" in result
