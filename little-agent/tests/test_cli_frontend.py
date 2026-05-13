"""Tests for CLI frontend (prompt_toolkit-based)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from prompt_toolkit import PromptSession

from little_agent.backends.exceptions import BackendTimeoutError
from little_agent.frontends.cli import CliClient
from little_agent.types import SessionUpdate

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client(inputs: list[Any]) -> CliClient:
    """Build a CliClient with a mocked PromptSession returning ``inputs`` in order.

    Each element in ``inputs`` is either:
    - a str  → returned as the typed line
    - EOFError  → raises EOFError (simulates Ctrl-D)
    - KeyboardInterrupt → raises KeyboardInterrupt (Ctrl-C)
    """
    mock_ps: MagicMock = MagicMock(spec=PromptSession)
    mock_ps.prompt_async = AsyncMock(side_effect=inputs)
    return CliClient(prompt_session=mock_ps)  # type: ignore[arg-type]


class _MockSession:
    def __init__(self, session_id: str = "sess-1") -> None:
        self.id = session_id
        self.cancel = AsyncMock()

    async def prompt(self, text: str) -> tuple[str, str]:
        return ("end_turn", f"resp:{text}")

    async def fork(self) -> "_MockSession":
        return _MockSession("sess-fork")

    def save(self) -> dict[str, object]:
        return {"id": self.id, "cwd": None, "chain": []}


class _MockAgent:
    def __init__(self) -> None:
        self.tools = MagicMock()
        self.tools.desc_tool.return_value = {"bash": MagicMock(desc="run shell")}
        self._sessions: list[_MockSession] = []

    async def new(self, cwd: str | None = None) -> _MockSession:
        sess = _MockSession(f"sess-{len(self._sessions)}")
        self._sessions.append(sess)
        return sess

    async def load(self, data: Any) -> _MockSession:
        return _MockSession("loaded")


# ---------------------------------------------------------------------------
# update() — buffering and output
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_agent_message_chunk(capsys: pytest.CaptureFixture[str]) -> None:
    """agent_message_chunk accumulates into buffer."""
    client = _make_client([])
    sess = _MockSession()
    await client.update(sess, SessionUpdate(type="agent_message_chunk", data={"text": "hello"}))
    client._flush_buffer()
    out = capsys.readouterr().out
    assert "[Agent] hello" in out


@pytest.mark.asyncio
async def test_update_thinking_chunk(capsys: pytest.CaptureFixture[str]) -> None:
    """thinking_chunk is prefixed with [Thinking]."""
    client = _make_client([])
    sess = _MockSession()
    await client.update(sess, SessionUpdate(type="thinking_chunk", data={"text": "hmm"}))
    client._flush_buffer()
    out = capsys.readouterr().out
    assert "[Thinking] hmm" in out


@pytest.mark.asyncio
async def test_update_tool_call(capsys: pytest.CaptureFixture[str]) -> None:
    """tool_call update prints [ToolCall] line."""
    client = _make_client([])
    sess = _MockSession()
    await client.update(
        sess,
        SessionUpdate(
            type="tool_call",
            data={"calls": {"c1": {"tool_name": "bash", "arguments": {"command": "ls"}}}},
        ),
    )
    out = capsys.readouterr().out
    assert "[ToolCall] c1: bash" in out
    assert "command: ls" in out


@pytest.mark.asyncio
async def test_update_tool_call_no_json_escaping(capsys: pytest.CaptureFixture[str]) -> None:
    """String arguments are printed as-is, not JSON-escaped."""
    client = _make_client([])
    sess = _MockSession()
    await client.update(
        sess,
        SessionUpdate(
            type="tool_call",
            data={"calls": {"c1": {"tool_name": "bash", "arguments": {"command": "echo hi"}}}},
        ),
    )
    out = capsys.readouterr().out
    assert "command: echo hi" in out


@pytest.mark.asyncio
async def test_update_tool_call_update(capsys: pytest.CaptureFixture[str]) -> None:
    """tool_call_update prints [ToolResult]."""
    client = _make_client([])
    sess = _MockSession()
    await client.update(
        sess,
        SessionUpdate(type="tool_call_update", data={"call_id": "c1", "status": "completed"}),
    )
    out = capsys.readouterr().out
    assert "[ToolResult] c1: completed" in out


@pytest.mark.asyncio
async def test_update_invalid_tool_call_type() -> None:
    """tool_call with non-dict calls raises ValueError."""
    client = _make_client([])
    sess = _MockSession()
    with pytest.raises(ValueError, match="'calls' must be a dict"):
        await client.update(sess, SessionUpdate(type="tool_call", data={"calls": "bad"}))


@pytest.mark.asyncio
async def test_coalesce_consecutive_agent_chunks(capsys: pytest.CaptureFixture[str]) -> None:
    """Multiple consecutive agent_message_chunks coalesce into one [Agent] line."""
    client = _make_client([])
    sess = _MockSession()
    await client.update(sess, SessionUpdate(type="agent_message_chunk", data={"text": "foo"}))
    await client.update(sess, SessionUpdate(type="agent_message_chunk", data={"text": "bar"}))
    client._flush_buffer()
    out = capsys.readouterr().out
    assert out.count("[Agent]") == 1
    assert "foobar" in out


@pytest.mark.asyncio
async def test_coalesce_consecutive_thinking_chunks(capsys: pytest.CaptureFixture[str]) -> None:
    """Consecutive thinking_chunks coalesce."""
    client = _make_client([])
    sess = _MockSession()
    await client.update(sess, SessionUpdate(type="thinking_chunk", data={"text": "a"}))
    await client.update(sess, SessionUpdate(type="thinking_chunk", data={"text": "b"}))
    client._flush_buffer()
    out = capsys.readouterr().out
    assert out.count("[Thinking]") == 1
    assert "ab" in out


@pytest.mark.asyncio
async def test_flush_on_type_switch(capsys: pytest.CaptureFixture[str]) -> None:
    """Switching from thinking to agent flushes the thinking buffer first."""
    client = _make_client([])
    sess = _MockSession()
    await client.update(sess, SessionUpdate(type="thinking_chunk", data={"text": "think"}))
    await client.update(sess, SessionUpdate(type="agent_message_chunk", data={"text": "answer"}))
    client._flush_buffer()
    out = capsys.readouterr().out
    assert "[Thinking] think" in out
    assert "[Agent] answer" in out


@pytest.mark.asyncio
async def test_flush_empty_buffer_is_noop(capsys: pytest.CaptureFixture[str]) -> None:
    """Flushing an empty buffer produces no output."""
    client = _make_client([])
    client._flush_buffer()
    out = capsys.readouterr().out
    assert out == ""


@pytest.mark.asyncio
async def test_flush_clears_buffer() -> None:
    """After flush, buffer is empty."""
    client = _make_client([])
    sess = _MockSession()
    await client.update(sess, SessionUpdate(type="agent_message_chunk", data={"text": "x"}))
    client._flush_buffer()
    assert client._buffer_type is None
    assert client._buffer_parts == []


@pytest.mark.asyncio
async def test_duplicate_agent_chunk_skipped(capsys: pytest.CaptureFixture[str]) -> None:
    """Exact duplicate agent chunk (non-streaming fallback) is skipped."""
    client = _make_client([])
    sess = _MockSession()
    await client.update(sess, SessionUpdate(type="agent_message_chunk", data={"text": "hi"}))
    # Same text: simulates non-streaming full-text replay — should be skipped
    await client.update(sess, SessionUpdate(type="agent_message_chunk", data={"text": "hi"}))
    client._flush_buffer()
    out = capsys.readouterr().out
    assert out.count("[Agent]") == 1


# ---------------------------------------------------------------------------
# request_permission
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_permission_granted() -> None:
    """'y' grants permission."""
    client = _make_client(["y"])
    sess = _MockSession()
    result = await client.request_permission(sess, "bash", {})
    assert result is True


@pytest.mark.asyncio
async def test_request_permission_denied() -> None:
    """'N' denies permission."""
    client = _make_client(["N"])
    sess = _MockSession()
    result = await client.request_permission(sess, "bash", {})
    assert result is False


@pytest.mark.asyncio
async def test_request_permission_eof() -> None:
    """EOFError denies permission."""
    client = _make_client([EOFError()])
    sess = _MockSession()
    result = await client.request_permission(sess, "bash", {})
    assert result is False


@pytest.mark.asyncio
async def test_request_permission_keyboard_interrupt() -> None:
    """KeyboardInterrupt denies permission."""
    client = _make_client([KeyboardInterrupt()])
    sess = _MockSession()
    result = await client.request_permission(sess, "bash", {})
    assert result is False


# ---------------------------------------------------------------------------
# _handle_command
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_command_quit(capsys: pytest.CaptureFixture[str]) -> None:
    client = _make_client([])
    agent = _MockAgent()
    sess = _MockSession()
    _, cont = await client._handle_command(agent, sess, "/quit")
    assert cont is False
    assert "Goodbye" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_handle_command_exit(capsys: pytest.CaptureFixture[str]) -> None:
    client = _make_client([])
    agent = _MockAgent()
    sess = _MockSession()
    _, cont = await client._handle_command(agent, sess, "/exit")
    assert cont is False


@pytest.mark.asyncio
async def test_handle_command_cancel() -> None:
    """'/cancel' calls session.cancel()."""
    client = _make_client([])
    agent = _MockAgent()
    sess = _MockSession()
    _, cont = await client._handle_command(agent, sess, "/cancel")
    assert cont is True
    sess.cancel.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_command_fork(capsys: pytest.CaptureFixture[str]) -> None:
    client = _make_client([])
    agent = _MockAgent()
    sess = _MockSession()
    new_sess, cont = await client._handle_command(agent, sess, "/fork")
    assert cont is True
    assert new_sess.id == "sess-fork"
    assert "Forked" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_handle_command_new(capsys: pytest.CaptureFixture[str]) -> None:
    client = _make_client([])
    agent = _MockAgent()
    sess = _MockSession()
    new_sess, cont = await client._handle_command(agent, sess, "/new")
    assert cont is True
    assert new_sess is not sess
    assert "Created" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_handle_command_list_tools(capsys: pytest.CaptureFixture[str]) -> None:
    client = _make_client([])
    agent = _MockAgent()
    sess = _MockSession()
    _, cont = await client._handle_command(agent, sess, "/list-tools")
    assert cont is True
    assert "bash" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_handle_command_unknown(capsys: pytest.CaptureFixture[str]) -> None:
    client = _make_client([])
    agent = _MockAgent()
    sess = _MockSession()
    _, cont = await client._handle_command(agent, sess, "/unknown")
    assert cont is True
    assert "Unknown command" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_do_save(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    client = _make_client([])
    sess = _MockSession()
    save_path = tmp_path / "out.json"
    await client._do_save(sess, save_path)
    assert save_path.exists()
    assert "saved" in capsys.readouterr().out.lower()


@pytest.mark.asyncio
async def test_do_load(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    client = _make_client([])
    agent = _MockAgent()
    sess = _MockSession()
    load_path = tmp_path / "sess.json"
    load_path.write_text(json.dumps({"id": "x", "chain": []}), encoding="utf-8")
    new_sess, ok = await client._do_load(agent, sess, load_path)
    assert ok is True
    assert "loaded" in capsys.readouterr().out.lower()


@pytest.mark.asyncio
async def test_do_save_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Errors during save are caught and printed."""
    client = _make_client([])
    bad_sess = MagicMock()
    bad_sess.save.side_effect = OSError("disk full")
    await client._do_save(bad_sess, tmp_path / "x.json")
    assert "[Error]" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_do_load_failure(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Load of missing file returns original session and ok=False."""
    client = _make_client([])
    agent = _MockAgent()
    original = _MockSession("orig")
    returned, ok = await client._do_load(agent, original, tmp_path / "missing.json")
    assert ok is False
    assert returned is original


@pytest.mark.asyncio
async def test_handle_command_load_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Load failure message printed via _handle_command."""
    client = _make_client([])
    agent = _MockAgent()
    sess = _MockSession()
    result_sess, cont = await client._handle_command(
        agent, sess, f"/load {tmp_path / 'missing.json'}"
    )
    assert cont is True
    assert result_sess is sess
    assert "Load failed" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# _do_prompt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_do_prompt_success(capsys: pytest.CaptureFixture[str]) -> None:
    """Successful prompt shows agent output."""
    client = _make_client([])
    sess = _MockSession()
    await client.update(sess, SessionUpdate(type="agent_message_chunk", data={"text": "result"}))
    await client._do_prompt(sess, "hi")
    out = capsys.readouterr().out
    assert "[Agent] result" in out


@pytest.mark.asyncio
async def test_do_prompt_cancelled(capsys: pytest.CaptureFixture[str]) -> None:
    """Cancelled turn prints [Cancelled]."""
    client = _make_client([])
    sess = MagicMock()
    sess.prompt = AsyncMock(return_value=("cancelled", "partial"))
    await client._do_prompt(sess, "hi")
    assert "[Cancelled]" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_do_prompt_cancel_via_cancelled_return(capsys: pytest.CaptureFixture[str]) -> None:
    """Cancelled stop_reason (session.cancel() path) prints [Cancelled]."""
    client = _make_client([])
    sess = MagicMock()
    sess.prompt = AsyncMock(return_value=("cancelled", "partial"))
    await client._do_prompt(sess, "hi")
    assert "[Cancelled]" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_do_prompt_timeout(capsys: pytest.CaptureFixture[str]) -> None:
    """BackendTimeoutError prints [Timeout]."""
    client = _make_client([])
    sess = MagicMock()
    sess.prompt = AsyncMock(side_effect=BackendTimeoutError("timeout"))
    await client._do_prompt(sess, "hi")
    assert "[Timeout]" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_do_prompt_generic_error(capsys: pytest.CaptureFixture[str]) -> None:
    """Generic exception prints [Error]."""
    client = _make_client([])
    sess = MagicMock()
    sess.prompt = AsyncMock(side_effect=RuntimeError("boom"))
    await client._do_prompt(sess, "hi")
    assert "[Error]" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# run() and _run_loop()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_quit_command(capsys: pytest.CaptureFixture[str]) -> None:
    """'/quit' exits the loop cleanly."""
    client = _make_client(["/quit"])
    agent = _MockAgent()
    await client.run(agent)
    assert "Goodbye" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_run_eof(capsys: pytest.CaptureFixture[str]) -> None:
    """EOF (Ctrl-D) exits the loop cleanly."""
    client = _make_client([EOFError()])
    agent = _MockAgent()
    await client.run(agent)
    assert "Goodbye" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_run_keyboard_interrupt_idle(capsys: pytest.CaptureFixture[str]) -> None:
    """KeyboardInterrupt at idle prompt exits cleanly."""
    client = _make_client([KeyboardInterrupt()])
    agent = _MockAgent()
    await client.run(agent)
    assert "Goodbye" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_run_prompt_and_quit(capsys: pytest.CaptureFixture[str]) -> None:
    """One prompt turn then /quit."""
    client = _make_client(["hello", "/quit"])
    agent = _MockAgent()
    await client.run(agent)
    out = capsys.readouterr().out
    assert "Goodbye" in out


@pytest.mark.asyncio
async def test_run_empty_input_skipped(capsys: pytest.CaptureFixture[str]) -> None:
    """Empty / whitespace-only input is skipped."""
    client = _make_client(["   ", "/quit"])
    agent = _MockAgent()
    await client.run(agent)
    # No "[Agent]" output expected since the empty line is skipped
    out = capsys.readouterr().out
    assert "Goodbye" in out


@pytest.mark.asyncio
async def test_run_cancel_command(capsys: pytest.CaptureFixture[str]) -> None:
    """/cancel calls session.cancel() then continues loop."""
    client = _make_client(["/cancel", "/quit"])
    agent = _MockAgent()
    await client.run(agent)
    # Session cancel was called (mock session tracks it)
    assert agent._sessions[0].cancel.called


@pytest.mark.asyncio
async def test_run_fork(capsys: pytest.CaptureFixture[str]) -> None:
    """/fork creates a new session then continues."""
    client = _make_client(["/fork", "/quit"])
    agent = _MockAgent()
    await client.run(agent)
    assert "Forked" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_run_new(capsys: pytest.CaptureFixture[str]) -> None:
    """/new replaces the current session."""
    client = _make_client(["/new", "/quit"])
    agent = _MockAgent()
    await client.run(agent)
    assert "Created" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_run_exit_alias(capsys: pytest.CaptureFixture[str]) -> None:
    """/exit is an alias for /quit."""
    client = _make_client(["/exit"])
    agent = _MockAgent()
    await client.run(agent)
    assert "Goodbye" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_run_list_tools(capsys: pytest.CaptureFixture[str]) -> None:
    """/list-tools prints available tools."""
    client = _make_client(["/list-tools", "/quit"])
    agent = _MockAgent()
    await client.run(agent)
    assert "bash" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_run_unknown_command(capsys: pytest.CaptureFixture[str]) -> None:
    """/unknown prints error message."""
    client = _make_client(["/nope", "/quit"])
    agent = _MockAgent()
    await client.run(agent)
    assert "Unknown command" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_run_save_and_load(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Save then load round-trip works via the run loop."""
    save_path = tmp_path / "sess.json"
    client = _make_client([f"/save {save_path}", f"/load {save_path}", "/quit"])
    agent = _MockAgent()
    await client.run(agent)
    out = capsys.readouterr().out
    assert "saved" in out.lower()
    assert "loaded" in out.lower()


@pytest.mark.asyncio
async def test_run_cancelled_prompt(capsys: pytest.CaptureFixture[str]) -> None:
    """A cancelled turn prints [Cancelled] and loop continues."""
    call_count = 0

    async def _prompt_async(prompt: str) -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return "> "  # prompt header line
        if call_count == 2:
            return "something"
        raise EOFError

    client = _make_client([])
    mock_ps: MagicMock = MagicMock(spec=PromptSession)
    mock_ps.prompt_async = _prompt_async  # type: ignore[assignment]
    client._prompt_session = mock_ps  # type: ignore[assignment]

    agent = _MockAgent()
    # Patch session.prompt to return cancelled
    original_new = agent.new

    async def patched_new(cwd: str | None = None) -> _MockSession:
        sess = await original_new(cwd=cwd)
        sess.prompt = AsyncMock(return_value=("cancelled", ""))
        return sess

    agent.new = patched_new  # type: ignore[method-assign]
    client = _make_client(["hello", EOFError()])
    agent2 = _MockAgent()
    sess_obj = await agent2.new()
    sess_obj.prompt = AsyncMock(return_value=("cancelled", ""))  # type: ignore[assignment]

    client2 = _make_client(["hello", EOFError()])
    agent3 = _MockAgent()

    async def new3(cwd: str | None = None) -> _MockSession:
        s = _MockSession()
        s.prompt = AsyncMock(return_value=("cancelled", ""))  # type: ignore[assignment]
        return s

    agent3.new = new3  # type: ignore[method-assign]
    await client2.run(agent3)
    out = capsys.readouterr().out
    assert "[Cancelled]" in out


@pytest.mark.asyncio
async def test_run_backend_timeout(capsys: pytest.CaptureFixture[str]) -> None:
    """BackendTimeoutError prints [Timeout]."""
    client = _make_client(["hello", EOFError()])
    agent = _MockAgent()

    async def new_timeout(cwd: str | None = None) -> _MockSession:
        s = _MockSession()
        s.prompt = AsyncMock(side_effect=BackendTimeoutError("timed out"))  # type: ignore[assignment]
        return s

    agent.new = new_timeout  # type: ignore[method-assign]
    await client.run(agent)
    assert "[Timeout]" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_initial_prompt_one_shot(capsys: pytest.CaptureFixture[str]) -> None:
    """--prompt mode sends one prompt then exits without entering the loop."""
    client = _make_client([])  # prompt_async never called
    agent = _MockAgent()
    await client.run(agent, initial_prompt="eval me")
    out = capsys.readouterr().out
    assert "> eval me" in out
    # prompt_async was NOT called (one-shot exits immediately)
    client._prompt_session.prompt_async.assert_not_awaited()  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_tool_call_flushes_agent_buffer(capsys: pytest.CaptureFixture[str]) -> None:
    """Receiving a tool_call update flushes any buffered agent text."""
    client = _make_client([])
    sess = _MockSession()
    await client.update(sess, SessionUpdate(type="agent_message_chunk", data={"text": "thinking"}))
    await client.update(
        sess,
        SessionUpdate(
            type="tool_call",
            data={"calls": {"c1": {"tool_name": "bash", "arguments": {}}}},
        ),
    )
    out = capsys.readouterr().out
    assert "[Agent] thinking" in out
    assert "[ToolCall]" in out


@pytest.mark.asyncio
async def test_tool_call_update_flushes_buffer(capsys: pytest.CaptureFixture[str]) -> None:
    """Receiving tool_call_update flushes buffered text."""
    client = _make_client([])
    sess = _MockSession()
    await client.update(sess, SessionUpdate(type="thinking_chunk", data={"text": "ponder"}))
    await client.update(
        sess,
        SessionUpdate(type="tool_call_update", data={"call_id": "c1", "status": "completed"}),
    )
    out = capsys.readouterr().out
    assert "[Thinking] ponder" in out
    assert "[ToolResult] c1: completed" in out


@pytest.mark.asyncio
async def test_non_streaming_agent_chunk_passes_through(capsys: pytest.CaptureFixture[str]) -> None:
    """A non-duplicate agent_message_chunk passes through normally."""
    client = _make_client([])
    sess = _MockSession()
    await client.update(sess, SessionUpdate(type="agent_message_chunk", data={"text": "line1"}))
    await client.update(sess, SessionUpdate(type="agent_message_chunk", data={"text": "line2"}))
    client._flush_buffer()
    out = capsys.readouterr().out
    assert "line1line2" in out


@pytest.mark.asyncio
async def test_tool_call_truncates_long_args(capsys: pytest.CaptureFixture[str]) -> None:
    """Arguments exceeding 5 lines are truncated with a count suffix."""
    client = _make_client([])
    sess = _MockSession()
    long_val = "\n".join(f"line{i}" for i in range(10))
    await client.update(
        sess,
        SessionUpdate(
            type="tool_call",
            data={"calls": {"c1": {"tool_name": "bash", "arguments": {"cmd": long_val}}}},
        ),
    )
    out = capsys.readouterr().out
    assert "lines..." in out
