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
    result = await provider.invoke("bash", {"command": "echo hello"})
    assert isinstance(result, str)
    assert "hello" in result


@pytest.mark.asyncio
async def test_bash_stderr_included() -> None:
    """Test bash tool includes stderr in output."""
    provider = BashToolProvider()
    result = await provider.invoke("bash", {"command": "echo error >&2"})
    assert isinstance(result, str)
    assert "error" in result


@pytest.mark.asyncio
async def test_bash_invalid_command_type_raises() -> None:
    """Test bash tool with non-string command raises ValueError."""
    provider = BashToolProvider()
    with pytest.raises(ValueError, match="command must be a string"):
        await provider.invoke("bash", {"command": 123})


@pytest.mark.asyncio
async def test_bash_unknown_tool_raises() -> None:
    """Test invoking unknown tool raises ValueError."""
    provider = BashToolProvider()
    with pytest.raises(ValueError, match="Unknown tool"):
        await provider.invoke("nonexistent", {})


@pytest.mark.asyncio
async def test_bash_timeout() -> None:
    """Test bash tool times out on long-running command."""
    provider = BashToolProvider()
    provider._TIMEOUT = 2  # Speed up test; default 30s is too slow for CI
    result = await provider.invoke("bash", {"command": "sleep 60"})
    assert isinstance(result, str)
    assert "timed out" in result


@pytest.mark.asyncio
async def test_bash_cwd() -> None:
    """Test bash tool uses custom working directory."""
    import os
    import tempfile

    provider = BashToolProvider()
    with tempfile.TemporaryDirectory() as tmpdir:
        result = await provider.invoke("bash", {"command": "pwd", "cwd": tmpdir})
        assert isinstance(result, str)
        assert os.path.realpath(tmpdir) in os.path.realpath(result.strip())


@pytest.mark.asyncio
async def test_bash_env() -> None:
    """Test bash tool passes custom environment variables merged with system env."""
    provider = BashToolProvider()
    result = await provider.invoke(
        "bash",
        {"command": "echo $LITTLE_AGENT_TEST_VAR", "env": {"LITTLE_AGENT_TEST_VAR": "hello123"}},
    )
    assert isinstance(result, str)
    assert "hello123" in result


@pytest.mark.asyncio
async def test_bash_stdin() -> None:
    """Test bash tool passes stdin to process."""
    provider = BashToolProvider()
    result = await provider.invoke("bash", {"command": "cat", "stdin": "hello from stdin"})
    assert isinstance(result, str)
    assert "hello from stdin" in result


@pytest.mark.asyncio
async def test_bash_backward_compat_no_new_params() -> None:
    """Test bash tool still works without the new optional params."""
    provider = BashToolProvider()
    result = await provider.invoke("bash", {"command": "echo compat"})
    assert isinstance(result, str)
    assert "compat" in result


def test_bash_tool_lists_new_params() -> None:
    """Test BashToolProvider lists cwd, env, stdin as optional parameters."""
    provider = BashToolProvider()
    tools = provider.list()
    bash_def = tools["bash"]
    arg_names = [arg[0] for arg in bash_def[1]]
    assert "cwd" in arg_names
    assert "env" in arg_names
    assert "stdin" in arg_names
    # Verify they are optional (required=False)
    arg_map = {arg[0]: arg[3] for arg in bash_def[1]}
    assert arg_map["cwd"] is False
    assert arg_map["env"] is False
    assert arg_map["stdin"] is False
