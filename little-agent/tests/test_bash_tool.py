"""Tests for bash tool provider."""

from __future__ import annotations

import logging

import pytest

from little_agent.agent.tool_manager import ToolManager
from little_agent.tools.bash import BashToolProvider


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
    provider = BashToolProvider(timeout=2)
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


# ---------------------------------------------------------------------------
# T77: dangerous env vars are filtered and a warning is emitted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bash_env_dangerous_vars_filtered(caplog: pytest.LogCaptureFixture) -> None:
    """Dangerous env vars (e.g. LD_PRELOAD) are stripped; safe vars pass through.

    The bash tool must:
    - NOT set LD_PRELOAD in the subprocess environment.
    - DO set MY_VAR in the subprocess environment.
    - Emit at least one logger.warning mentioning the blocked key.
    """
    mgr = _make_manager()
    with caplog.at_level(logging.WARNING, logger="little_agent.tools.bash"):
        result = await mgr["bash"](
            {
                "command": "echo LD=${LD_PRELOAD:-ABSENT}; echo MY=${MY_VAR:-ABSENT}",
                "env": {"LD_PRELOAD": "/evil.so", "MY_VAR": "ok"},
            }
        )

    assert isinstance(result, dict)
    stdout = result.get("stdout", "")

    # LD_PRELOAD must not reach the subprocess.
    assert "LD=ABSENT" in stdout, f"LD_PRELOAD must be blocked; subprocess stdout: {stdout!r}"

    # MY_VAR must reach the subprocess.
    assert "MY=ok" in stdout, f"MY_VAR must be forwarded to subprocess; stdout: {stdout!r}"

    # A warning must have been emitted about the blocked var.
    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warning_records, "Expected a warning for blocked dangerous env var"
    assert any("LD_PRELOAD" in r.message for r in warning_records), (
        f"Warning should mention 'LD_PRELOAD'; got: {[r.message for r in warning_records]}"
    )


# ---------------------------------------------------------------------------
# S-1: bash tool timeout configurable
# ---------------------------------------------------------------------------


def test_bash_default_timeout_values() -> None:
    """BashToolProvider default timeout is 30s, max_timeout is 1800s."""
    provider = BashToolProvider()
    assert provider._timeout == 30
    assert provider._max_timeout == 1800


def test_bash_custom_timeout_init() -> None:
    """BashToolProvider accepts custom timeout and max_timeout."""
    provider = BashToolProvider(timeout=60, max_timeout=3600)
    assert provider._timeout == 60
    assert provider._max_timeout == 3600


def test_bash_tool_lists_timeout_param() -> None:
    """BashToolProvider includes optional 'timeout' parameter in ToolDef."""
    provider = BashToolProvider()
    tools = {name: tooldef for name, tooldef, _ in provider}
    bash_def = tools["bash"]
    arg_names = [arg.name for arg in bash_def.args]
    assert "timeout" in arg_names
    timeout_arg = next(a for a in bash_def.args if a.name == "timeout")
    assert timeout_arg.required is False
    assert timeout_arg.type == "integer"


@pytest.mark.asyncio
async def test_bash_per_call_timeout_override() -> None:
    """Per-call timeout arg (within max_timeout) is used instead of default."""
    provider = BashToolProvider(timeout=30, max_timeout=60)
    mgr = ToolManager()
    mgr.register(provider)
    # Passes a timeout of 5s; sleep 0.1s is well within that
    result = await mgr["bash"]({"command": "echo ok", "timeout": 5})
    assert isinstance(result, dict)
    assert result["returncode"] == 0


@pytest.mark.asyncio
async def test_bash_timeout_clamped_to_max(caplog: pytest.LogCaptureFixture) -> None:
    """Per-call timeout exceeding max_timeout is clamped with a WARNING."""
    provider = BashToolProvider(timeout=10, max_timeout=20)
    mgr = ToolManager()
    mgr.register(provider)
    with caplog.at_level(logging.WARNING, logger="little_agent.tools.bash"):
        result = await mgr["bash"]({"command": "echo clamped", "timeout": 9999})
    assert isinstance(result, dict)
    assert result["returncode"] == 0
    assert any("clamping" in r.message or "max_timeout" in r.message for r in caplog.records), (
        "Expected a WARNING about clamping"
    )


@pytest.mark.asyncio
async def test_bash_config_timeout_kills_process() -> None:
    """BashToolProvider with low timeout kills long-running process."""
    provider = BashToolProvider(timeout=1, max_timeout=10)
    mgr = ToolManager()
    mgr.register(provider)
    result = await mgr["bash"]({"command": "sleep 60"})
    assert isinstance(result, dict)
    assert "timed out" in result["stderr"]
    assert result["returncode"] == -1
