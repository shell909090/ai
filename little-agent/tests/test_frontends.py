"""Tests for frontend clients."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from little_agent.frontends.cli import CliClient, _setup_readline
from little_agent.frontends.protocol import SessionUpdate
from tests.mocks import MockAgent, MockToolProvider


@pytest.fixture(autouse=True)
def _isolate_readline():
    """Mock readline to avoid touching the real history file.

    Without this, every client.run test reads and rewrites the history file, and because
    read_history_file appends rather than replaces the in-memory list, the file grows
    exponentially across the suite and thrashes the disk.
    """
    with patch.dict("sys.modules", {"readline": MagicMock()}):
        yield


@pytest.mark.asyncio
async def test_cli_client_collects_updates() -> None:
    """Test CliClient collects updates."""
    client = CliClient()
    update = SessionUpdate(type="agent_message_chunk", data={"text": "hello"})
    await client.update(None, update)  # type: ignore[arg-type]
    assert len(client._updates) == 1
    assert client._updates[0].type == "agent_message_chunk"


@pytest.mark.asyncio
async def test_cli_update_tool_call() -> None:
    """Test CliClient.update with tool_call prints correctly."""
    client = CliClient()
    update = SessionUpdate(
        type="tool_call",
        data={"calls": {"c1": {"tool_name": "echo", "arguments": {"text": "hello"}}}},
    )
    with patch("builtins.print") as mock_print:
        await client.update(None, update)  # type: ignore[arg-type]
    mock_print.assert_any_call("[ToolCall] c1: echo")
    printed = [call.args[0] for call in mock_print.call_args_list]
    assert printed[1] == "text: hello"


@pytest.mark.asyncio
async def test_cli_update_tool_call_truncated() -> None:
    """Test CliClient.update truncates long tool_call arguments at 5 lines."""
    client = CliClient()
    from little_agent.types import JSONValue

    args: dict[str, JSONValue] = {
        "line1": "a",
        "line2": "b",
        "line3": "c",
        "line4": "d",
        "line5": "e",
        "line6": "f",
    }
    update = SessionUpdate(
        type="tool_call",
        data={"calls": {"c1": {"tool_name": "echo", "arguments": args}}},
    )
    with patch("builtins.print") as mock_print:
        await client.update(None, update)  # type: ignore[arg-type]
    mock_print.assert_any_call("[ToolCall] c1: echo")
    printed = [call.args[0] for call in mock_print.call_args_list]
    args_text = printed[1]
    assert "...1 lines..." in args_text


@pytest.mark.asyncio
async def test_cli_update_thinking_chunk() -> None:
    """thinking_chunk is buffered; _flush_buffer emits stripped output."""
    client = CliClient()
    update = SessionUpdate(type="thinking_chunk", data={"text": "  thinking...  "})
    with patch("builtins.print") as mock_print:
        await client.update(None, update)  # type: ignore[arg-type]
    mock_print.assert_not_called()
    with patch("builtins.print") as mock_print2:
        client._flush_buffer()
    mock_print2.assert_called_once_with("[Thinking] thinking...")


@pytest.mark.asyncio
async def test_cli_update_agent_message_strip() -> None:
    """agent_message_chunk is buffered; _flush_buffer emits stripped output."""
    client = CliClient()
    update = SessionUpdate(type="agent_message_chunk", data={"text": "  hello  "})
    with patch("builtins.print") as mock_print:
        await client.update(None, update)  # type: ignore[arg-type]
    mock_print.assert_not_called()
    with patch("builtins.print") as mock_print2:
        client._flush_buffer()
    mock_print2.assert_called_once_with("[Agent] hello")


@pytest.mark.asyncio
async def test_cli_update_tool_call_update() -> None:
    """Test CliClient.update with tool_call_update prints correctly."""
    client = CliClient()
    update = SessionUpdate(type="tool_call_update", data={"call_id": "c1", "status": "completed"})
    with patch("builtins.print") as mock_print:
        await client.update(None, update)  # type: ignore[arg-type]
        mock_print.assert_called_once_with("[ToolResult] c1: completed")


@pytest.mark.asyncio
async def test_cli_request_permission() -> None:
    """Test CliClient.request_permission returns True when user answers 'y'."""
    client = CliClient()
    with patch("asyncio.to_thread", return_value="y"):
        result = await client.request_permission(None, "test", {})  # type: ignore[arg-type]
    assert result is True


@pytest.mark.asyncio
async def test_cli_run_quit() -> None:
    """Test CliClient.run exits on /quit."""
    client = CliClient()
    agent = MockAgent()

    with patch("asyncio.to_thread", return_value="/quit"):
        with patch("builtins.print"):
            await client.run(agent)


@pytest.mark.asyncio
async def test_cli_run_eof() -> None:
    """Test CliClient.run exits on EOFError."""
    client = CliClient()
    agent = MockAgent()

    with patch("asyncio.to_thread", side_effect=EOFError()):
        with patch("builtins.print"):
            await client.run(agent)


@pytest.mark.asyncio
async def test_cli_run_empty_input() -> None:
    """Test CliClient.run skips empty input."""
    client = CliClient()
    agent = MockAgent()

    with patch("asyncio.to_thread", side_effect=["", "/quit"]):
        with patch("builtins.print"):
            await client.run(agent)


@pytest.mark.asyncio
async def test_cli_run_cancel() -> None:
    """Test CliClient.run handles /cancel."""
    client = CliClient()
    agent = MockAgent()

    with patch("asyncio.to_thread", side_effect=["/cancel", "/quit"]):
        with patch("builtins.print"):
            await client.run(agent)


@pytest.mark.asyncio
async def test_cli_run_fork() -> None:
    """Test CliClient.run handles /fork."""
    client = CliClient()
    agent = MockAgent()

    with patch("asyncio.to_thread", side_effect=["/fork", "/quit"]):
        with patch("builtins.print") as mock_print:
            await client.run(agent)

    mock_print.assert_any_call("Forked new session.")


@pytest.mark.asyncio
async def test_cli_run_prompt_error() -> None:
    """Test CliClient.run handles exception during prompt."""
    client = CliClient()
    agent = MockAgent()
    agent._agent.new = AsyncMock(return_value=MagicMock())  # type: ignore[method-assign]
    session = await agent._agent.new()
    session.prompt = AsyncMock(side_effect=ValueError("bad prompt"))
    agent.new = AsyncMock(return_value=session)  # type: ignore[method-assign]

    with patch("asyncio.to_thread", side_effect=["hello", "/quit"]):
        with patch("builtins.print") as mock_print:
            await client.run(agent)

    mock_print.assert_any_call("[Error] bad prompt")


@pytest.mark.asyncio
async def test_cli_run_new() -> None:
    """Test CliClient.run handles /new."""
    client = CliClient()
    agent = MockAgent()

    with patch("asyncio.to_thread", side_effect=["/new", "/quit"]):
        with patch("builtins.print") as mock_print:
            await client.run(agent)

    mock_print.assert_any_call("Created new session.")


@pytest.mark.asyncio
async def test_cli_run_save_and_load(tmp_path: Path) -> None:
    """Test CliClient.run handles /save and /load."""
    client = CliClient()
    agent = MockAgent()
    save_path = tmp_path / "session.json"

    with patch("asyncio.to_thread", side_effect=[f"/save {save_path}", "/quit"]):
        with patch("builtins.print") as mock_print:
            await client.run(agent)

    mock_print.assert_any_call(f"Session saved to {save_path}")
    assert save_path.exists()

    with patch("asyncio.to_thread", side_effect=[f"/load {save_path}", "/quit"]):
        with patch("builtins.print") as mock_print2:
            await client.run(agent)

    mock_print2.assert_any_call(f"Session loaded from {save_path}")


@pytest.mark.asyncio
async def test_cli_run_success_path() -> None:
    """Test CliClient.run successful prompt path."""
    client = CliClient()
    agent = MockAgent()

    with patch("asyncio.to_thread", side_effect=["hello", "/quit"]):
        with patch("builtins.print"):
            await client.run(agent)


@pytest.mark.asyncio
async def test_cli_run_exit() -> None:
    """Test CliClient.run exits on /exit (alias for /quit)."""
    client = CliClient()
    agent = MockAgent()

    with patch("asyncio.to_thread", return_value="/exit"):
        with patch("builtins.print") as mock_print:
            await client.run(agent)

    mock_print.assert_any_call("Goodbye!")


@pytest.mark.asyncio
async def test_cli_run_list_tools() -> None:
    """Test CliClient.run handles /list-tools."""
    from little_agent.tools.protocol import ToolArgDef, ToolDef

    client = CliClient()
    tools = {"echo": ToolDef(desc="Echo tool", args=[ToolArgDef("text", "string", "text", True)])}
    agent = MockAgent(tools=MockToolProvider(tools=tools))

    with patch("asyncio.to_thread", side_effect=["/list-tools", "/quit"]):
        with patch("builtins.print") as mock_print:
            await client.run(agent)

    mock_print.assert_any_call("Available tools:")
    mock_print.assert_any_call("  echo: Echo tool")


@pytest.mark.asyncio
async def test_cli_run_unknown_command() -> None:
    """Test CliClient.run prints hint for unknown / commands."""
    client = CliClient()
    agent = MockAgent()

    with patch("asyncio.to_thread", side_effect=["/typo", "/quit"]):
        with patch("builtins.print") as mock_print:
            await client.run(agent)

    mock_print.assert_any_call("Unknown command: /typo")


@pytest.mark.asyncio
async def test_cli_run_cancelled() -> None:
    """Test CliClient.run prints [Cancelled] when prompt returns cancelled."""
    client = CliClient()
    agent = MockAgent()
    agent._agent.new = AsyncMock(return_value=MagicMock())  # type: ignore[method-assign]
    session = await agent._agent.new()
    session.prompt = AsyncMock(return_value=("cancelled", ""))
    agent.new = AsyncMock(return_value=session)  # type: ignore[method-assign]

    with patch("asyncio.to_thread", side_effect=["hello", "/quit"]):
        with patch("builtins.print") as mock_print:
            await client.run(agent)

    mock_print.assert_any_call("[Cancelled]")


def test_setup_readline_does_not_raise() -> None:
    """_setup_readline completes without error on all platforms."""
    result = _setup_readline()
    # Returns a Path if readline is available, None otherwise
    from pathlib import Path

    assert result is None or isinstance(result, Path)


@pytest.mark.asyncio
async def test_cli_run_backend_timeout_error() -> None:
    """Test CliClient.run prints [Timeout] on BackendTimeoutError."""
    from little_agent.backends.exceptions import BackendTimeoutError

    client = CliClient()
    agent = MockAgent()
    agent._agent.new = AsyncMock(return_value=MagicMock())  # type: ignore[method-assign]
    session = await agent._agent.new()
    session.prompt = AsyncMock(side_effect=BackendTimeoutError("timed out after 60s"))
    agent.new = AsyncMock(return_value=session)  # type: ignore[method-assign]

    with patch("asyncio.to_thread", side_effect=["hello", "/quit"]):
        with patch("builtins.print") as mock_print:
            await client.run(agent)

    printed = [str(call.args[0]) for call in mock_print.call_args_list]
    assert any("[Timeout]" in p for p in printed)
