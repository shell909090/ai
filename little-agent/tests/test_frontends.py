"""Tests for frontend clients."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from little_agent.frontends.cli import CliClient
from little_agent.frontends.protocol import SessionUpdate
from tests.mocks import MockAgent


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
    update = SessionUpdate(type="tool_call", data={"calls": {"c1": {"tool_name": "echo"}}})
    with patch("builtins.print") as mock_print:
        await client.update(None, update)  # type: ignore[arg-type]
        mock_print.assert_called_once_with("[ToolCall] c1: echo")


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
    """Test CliClient.request_permission returns True."""
    client = CliClient()
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
    agent._agent.new = AsyncMock(return_value=MagicMock())
    session = await agent._agent.new()
    session.prompt = AsyncMock(side_effect=ValueError("bad prompt"))
    agent.new = AsyncMock(return_value=session)

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
async def test_cli_run_save_and_load(tmp_path) -> None:
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
