"""Tests for bash tool provider."""

from __future__ import annotations

import pytest

from little_agent.tools.bash import BashToolProvider
from little_agent.tools.manager import ToolManager


def _make_manager() -> ToolManager:
    mgr = ToolManager()
    mgr.register(BashToolProvider())
    return mgr


def test_bash_list() -> None:
    """Test BashToolProvider exposes bash tool via __iter__."""
    provider = BashToolProvider()
    tools = {name: tooldef for name, tooldef, _ in provider}
    assert "bash" in tools
    assert any(arg.name == "command" for arg in tools["bash"].args)


@pytest.mark.asyncio
async def test_bash_echo() -> None:
    """Test bash tool executes echo command."""
    mgr = _make_manager()
    result = await mgr["bash"]({"command": "echo hello"})
    assert isinstance(result, dict)
    assert "hello" in result["stdout"]
    assert result["returncode"] == 0


@pytest.mark.asyncio
async def test_bash_stderr_included() -> None:
    """Test bash tool includes stderr in output."""
    mgr = _make_manager()
    result = await mgr["bash"]({"command": "echo error >&2"})
    assert isinstance(result, dict)
    assert "error" in result["stderr"]
    assert result["returncode"] == 0


@pytest.mark.asyncio
async def test_bash_invalid_command_type_raises() -> None:
    """Test bash tool with non-string command raises ValueError."""
    mgr = _make_manager()
    with pytest.raises(ValueError, match="command must be a string"):
        await mgr["bash"]({"command": 123})


def test_bash_unknown_tool_raises() -> None:
    """Test invoking unknown tool raises KeyError."""
    mgr = _make_manager()
    with pytest.raises(KeyError):
        mgr["nonexistent"]


@pytest.mark.asyncio
async def test_bash_timeout() -> None:
    """Test bash tool times out on long-running command."""
    provider = BashToolProvider()
    provider._TIMEOUT = 2  # Speed up test; default 30s is too slow for CI
    mgr = ToolManager()
    mgr.register(provider)
    result = await mgr["bash"]({"command": "sleep 60"})
    assert isinstance(result, dict)
    assert "timed out" in result["stderr"]
    assert result["returncode"] == -1


@pytest.mark.asyncio
async def test_bash_cwd() -> None:
    """Test bash tool uses custom working directory."""
    import os
    import tempfile

    mgr = _make_manager()
    with tempfile.TemporaryDirectory() as tmpdir:
        result = await mgr["bash"]({"command": "pwd", "cwd": tmpdir})
        assert isinstance(result, dict)
        assert os.path.realpath(tmpdir) in os.path.realpath(result["stdout"].strip())
        assert result["returncode"] == 0


@pytest.mark.asyncio
async def test_bash_env() -> None:
    """Test bash tool passes custom environment variables merged with system env."""
    mgr = _make_manager()
    result = await mgr["bash"](
        {"command": "echo $LITTLE_AGENT_TEST_VAR", "env": {"LITTLE_AGENT_TEST_VAR": "hello123"}}
    )
    assert isinstance(result, dict)
    assert "hello123" in result["stdout"]
    assert result["returncode"] == 0


@pytest.mark.asyncio
async def test_bash_stdin() -> None:
    """Test bash tool passes stdin to process."""
    mgr = _make_manager()
    result = await mgr["bash"]({"command": "cat", "stdin": "hello from stdin"})
    assert isinstance(result, dict)
    assert "hello from stdin" in result["stdout"]
    assert result["returncode"] == 0


@pytest.mark.asyncio
async def test_bash_backward_compat_no_new_params() -> None:
    """Test bash tool still works without the new optional params."""
    mgr = _make_manager()
    result = await mgr["bash"]({"command": "echo compat"})
    assert isinstance(result, dict)
    assert "compat" in result["stdout"]
    assert result["returncode"] == 0


def test_bash_tool_lists_new_params() -> None:
    """Test BashToolProvider lists cwd, env, stdin as optional parameters."""
    provider = BashToolProvider()
    tools = {name: tooldef for name, tooldef, _ in provider}
    bash_def = tools["bash"]
    arg_names = [arg.name for arg in bash_def.args]
    assert "cwd" in arg_names
    assert "env" in arg_names
    assert "stdin" in arg_names
    arg_map = {arg.name: arg.required for arg in bash_def.args}
    assert arg_map["cwd"] is False
    assert arg_map["env"] is False
    assert arg_map["stdin"] is False
