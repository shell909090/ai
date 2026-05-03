"""Tests for CLI frontend."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from little_agent.backends.exceptions import BackendTimeoutError
from little_agent.frontends.cli import CliClient, _setup_readline
from little_agent.types import SessionUpdate


class _MockSession:
    """Mock session for CLI testing."""

    def __init__(self, session_id: str = "sess-1") -> None:
        self.id = session_id
        self._cancelled = False

    async def prompt(self, text: str) -> tuple[str, str]:
        return ("end_turn", f"response-to-{text}")

    async def cancel(self) -> None:
        self._cancelled = True

    async def fork(self) -> "_MockSession":
        return _MockSession(session_id="sess-fork")

    def save(self) -> dict[str, object]:
        return {"id": self.id, "cwd": "/tmp", "chain": []}


class _MockAgent:
    """Mock agent for CLI testing."""

    def __init__(self) -> None:
        self.tools = MagicMock()
        self.tools.list.return_value = {
            "bash": ("Run shell commands", []),
            "read": ("Read files", []),
        }
        self._session_count = 0

    async def new(self, cwd: str | None = None) -> _MockSession:
        self._session_count += 1
        return _MockSession(session_id=f"sess-{self._session_count}")

    async def load(self, data: object) -> _MockSession:
        return _MockSession(session_id="sess-loaded")


@pytest.fixture
def client() -> CliClient:
    return CliClient()


@pytest.fixture
def agent() -> _MockAgent:
    return _MockAgent()


@pytest.fixture
def session() -> _MockSession:
    return _MockSession()


# --- update() tests ---


def test_update_agent_message_chunk(client: CliClient, session: _MockSession) -> None:
    """update() prints agent message chunk."""
    with patch("builtins.print") as mock_print:
        asyncio.run(
            client.update(
                session,
                SessionUpdate(type="agent_message_chunk", data={"text": "hello"}),
            )
        )
    mock_print.assert_called_once_with("[Agent] hello")


def test_update_thinking_chunk(client: CliClient, session: _MockSession) -> None:
    """update() prints thinking chunk."""
    with patch("builtins.print") as mock_print:
        asyncio.run(
            client.update(
                session,
                SessionUpdate(type="thinking_chunk", data={"text": "thinking..."}),
            )
        )
    mock_print.assert_called_once_with("[Thinking] thinking...")


def test_update_tool_call(client: CliClient, session: _MockSession) -> None:
    """update() prints tool calls."""
    with patch("builtins.print") as mock_print:
        asyncio.run(
            client.update(
                session,
                SessionUpdate(
                    type="tool_call",
                    data={"calls": {"c1": {"tool_name": "bash", "arguments": {"cmd": "ls"}}}},
                ),
            )
        )
    calls = [c[0][0] for c in mock_print.call_args_list]
    assert any("ToolCall" in c for c in calls)


def test_update_tool_call_update(client: CliClient, session: _MockSession) -> None:
    """update() prints tool call update."""
    with patch("builtins.print") as mock_print:
        asyncio.run(
            client.update(
                session,
                SessionUpdate(
                    type="tool_call_update",
                    data={"call_id": "c1", "status": "completed"},
                ),
            )
        )
    mock_print.assert_called_once_with("[ToolResult] c1: completed")


def test_update_invalid_tool_call_type(client: CliClient, session: _MockSession) -> None:
    """update() raises ValueError for invalid tool_call calls type."""
    with pytest.raises(ValueError, match="must be a dict"):
        asyncio.run(
            client.update(
                session,
                SessionUpdate(type="tool_call", data={"calls": "not-a-dict"}),
            )
        )


# --- request_permission() tests ---


@pytest.mark.asyncio
async def test_request_permission_granted(client: CliClient, session: _MockSession) -> None:
    """request_permission returns True when user answers 'y'."""
    with patch("asyncio.to_thread", return_value="y"):
        result = await client.request_permission(session, "bash", {})
    assert result is True


@pytest.mark.asyncio
async def test_request_permission_denied(client: CliClient, session: _MockSession) -> None:
    """request_permission returns False when user answers 'n'."""
    with patch("asyncio.to_thread", return_value="n"):
        result = await client.request_permission(session, "bash", {})
    assert result is False


@pytest.mark.asyncio
async def test_request_permission_eof(client: CliClient, session: _MockSession) -> None:
    """request_permission returns False on EOFError."""
    with patch("asyncio.to_thread", side_effect=EOFError):
        result = await client.request_permission(session, "bash", {})
    assert result is False


# --- _handle_command() tests ---


@pytest.mark.asyncio
async def test_handle_command_quit(
    client: CliClient, agent: _MockAgent, session: _MockSession
) -> None:
    """/quit exits the loop."""
    sess, cont = await client._handle_command(agent, session, "/quit")
    assert cont is False


@pytest.mark.asyncio
async def test_handle_command_exit(
    client: CliClient, agent: _MockAgent, session: _MockSession
) -> None:
    """/exit exits the loop."""
    sess, cont = await client._handle_command(agent, session, "/exit")
    assert cont is False


@pytest.mark.asyncio
async def test_handle_command_cancel(
    client: CliClient, agent: _MockAgent, session: _MockSession
) -> None:
    """/cancel calls session.cancel()."""
    sess, cont = await client._handle_command(agent, session, "/cancel")
    assert cont is True
    assert session._cancelled is True


@pytest.mark.asyncio
async def test_handle_command_fork(
    client: CliClient, agent: _MockAgent, session: _MockSession
) -> None:
    """/fork creates a new forked session."""
    sess, cont = await client._handle_command(agent, session, "/fork")
    assert cont is True
    assert sess.id == "sess-fork"


@pytest.mark.asyncio
async def test_handle_command_new(
    client: CliClient, agent: _MockAgent, session: _MockSession
) -> None:
    """/new creates a new session via agent.new()."""
    sess, cont = await client._handle_command(agent, session, "/new")
    assert cont is True
    assert sess.id == "sess-1"


@pytest.mark.asyncio
async def test_handle_command_list_tools(
    client: CliClient, agent: _MockAgent, session: _MockSession
) -> None:
    """/list-tools prints available tools."""
    with patch("builtins.print") as mock_print:
        sess, cont = await client._handle_command(agent, session, "/list-tools")
    assert cont is True
    calls = [c[0][0] for c in mock_print.call_args_list]
    assert any("bash" in c for c in calls)


@pytest.mark.asyncio
async def test_handle_command_unknown(
    client: CliClient, agent: _MockAgent, session: _MockSession
) -> None:
    """Unknown command prints error."""
    with patch("builtins.print") as mock_print:
        sess, cont = await client._handle_command(agent, session, "/unknown")
    assert cont is True
    mock_print.assert_called_once_with("Unknown command: /unknown")


# --- _do_save / _do_load tests ---


@pytest.mark.asyncio
async def test_do_save(tmp_path: Path, client: CliClient, session: _MockSession) -> None:
    """_do_save writes session data to file."""
    path = tmp_path / "session.json"
    with patch("builtins.print"):
        await client._do_save(session, path)
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["id"] == "sess-1"


@pytest.mark.asyncio
async def test_do_load(
    tmp_path: Path, client: CliClient, agent: _MockAgent, session: _MockSession
) -> None:
    """_do_load reads session data from file."""
    path = tmp_path / "session.json"
    path.write_text(json.dumps({"id": "loaded", "cwd": "/tmp", "chain": []}))
    with patch("builtins.print"):
        sess = await client._do_load(agent, session, path)
    assert sess.id == "sess-loaded"


@pytest.mark.asyncio
async def test_do_save_error(client: CliClient, session: _MockSession) -> None:
    """_do_save handles errors gracefully."""
    with patch("builtins.print") as mock_print:
        await client._do_save(session, Path("/nonexistent/dir/session.json"))
    calls = [c[0][0] for c in mock_print.call_args_list]
    assert any("[Error]" in c for c in calls)


# --- _do_prompt tests ---


@pytest.mark.asyncio
async def test_do_prompt_success(client: CliClient, session: _MockSession) -> None:
    """_do_prompt sends input and prints result."""
    with patch("builtins.print") as mock_print:
        await client._do_prompt(session, "hello")
    # No explicit print on success, only debug logging
    mock_print.assert_not_called()


@pytest.mark.asyncio
async def test_do_prompt_cancelled(client: CliClient) -> None:
    """_do_prompt prints [Cancelled] when stop_reason is cancelled."""
    sess = _MockSession()

    async def _cancelled_prompt(text: str) -> tuple[str, str]:
        return ("cancelled", "")

    sess.prompt = _cancelled_prompt  # type: ignore[method-assign]
    with patch("builtins.print") as mock_print:
        await client._do_prompt(sess, "hello")
    mock_print.assert_called_once_with("[Cancelled]")


@pytest.mark.asyncio
async def test_do_prompt_timeout(client: CliClient, session: _MockSession) -> None:
    """_do_prompt handles BackendTimeoutError."""

    async def _timeout_prompt(text: str) -> tuple[str, str]:
        raise BackendTimeoutError("backend timeout")

    session.prompt = _timeout_prompt  # type: ignore[method-assign]
    with patch("builtins.print") as mock_print:
        await client._do_prompt(session, "hello")
    mock_print.assert_called_once_with("[Timeout] backend timeout")


@pytest.mark.asyncio
async def test_do_prompt_error(client: CliClient, session: _MockSession) -> None:
    """_do_prompt handles generic exceptions."""

    async def _error_prompt(text: str) -> tuple[str, str]:
        raise RuntimeError("boom")

    session.prompt = _error_prompt  # type: ignore[method-assign]
    with patch("builtins.print") as mock_print:
        await client._do_prompt(session, "hello")
    calls = [c[0][0] for c in mock_print.call_args_list]
    assert any("[Error]" in c for c in calls)


# --- run() integration tests ---


@pytest.mark.asyncio
async def test_run_quit_command(client: CliClient, agent: _MockAgent) -> None:
    """run() exits on /quit command."""
    inputs = ["/quit"]
    with patch("asyncio.to_thread", side_effect=lambda _, prompt: inputs.pop(0)):
        with patch("builtins.print"):
            await client.run(agent)


@pytest.mark.asyncio
async def test_run_eof(client: CliClient, agent: _MockAgent) -> None:
    """run() exits on EOF."""
    with patch("asyncio.to_thread", side_effect=EOFError):
        with patch("builtins.print"):
            await client.run(agent)


@pytest.mark.asyncio
async def test_run_prompt_and_command(client: CliClient, agent: _MockAgent) -> None:
    """run() handles prompt then command."""
    inputs = ["hello", "/quit"]
    with patch("asyncio.to_thread", side_effect=lambda _, prompt: inputs.pop(0)):
        with patch("builtins.print"):
            await client.run(agent)


# --- _setup_readline tests ---


def test_setup_readline_returns_path() -> None:
    """_setup_readline returns history file path when readline is available."""
    with patch.dict("sys.modules", {"readline": MagicMock()}):
        path = _setup_readline()
    assert path is not None
    assert path.name == ".little_agent_history"


def test_setup_readline_import_error() -> None:
    """_setup_readline returns None when readline is not available."""
    with patch.dict("sys.modules", {"readline": None}):
        path = _setup_readline()
    assert path is None
