"""Tests for ACP frontend."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from little_agent.frontends.acp import AcpClient
from little_agent.frontends.protocol import SessionUpdate
from tests.mocks import MockAgent


@pytest.mark.asyncio
async def test_write_json_outputs_single_line(capsys: pytest.CaptureFixture[str]) -> None:
    """AcpClient._write_json writes one line of JSON to stdout."""
    client = AcpClient()
    await client._write_json({"key": "value"})
    out = capsys.readouterr().out
    assert out.endswith("\n")
    parsed = json.loads(out.strip())
    assert parsed == {"key": "value"}


@pytest.mark.asyncio
async def test_acp_update_writes_json(capsys: pytest.CaptureFixture[str]) -> None:
    """AcpClient.update writes session/update JSON to stdout."""
    client = AcpClient()
    mock_session = MagicMock()
    mock_session.id = "sess-1"
    update = SessionUpdate(type="agent_message_chunk", data={"text": "hello"})
    await client.update(mock_session, update)  # type: ignore[arg-type]
    out = capsys.readouterr().out
    msg = json.loads(out.strip())
    assert msg["type"] == "session/update"
    assert msg["session_id"] == "sess-1"
    assert msg["update"]["type"] == "agent_message_chunk"


@pytest.mark.asyncio
async def test_acp_request_permission_granted_by_default() -> None:
    """AcpClient.request_permission sends request and returns True when responded."""
    client = AcpClient()
    mock_session = MagicMock()
    mock_session.id = "sess-1"

    payload = {}
    # Start permission request in background
    perm_task = asyncio.create_task(
        client.request_permission(mock_session, "bash", payload)  # type: ignore[arg-type]
    )

    # Simulate permission response with matching req_id
    await asyncio.sleep(0.05)
    req_id = f"perm_sess-1_bash_{id(payload)}"
    client._handle_permission_response({"id": req_id, "granted": True})

    result = await asyncio.wait_for(perm_task, timeout=1.0)
    assert result is True


@pytest.mark.asyncio
async def test_acp_session_new(capsys: pytest.CaptureFixture[str]) -> None:
    """session/new creates a session and returns session_id."""
    client = AcpClient()
    agent = MockAgent()
    response = await client._handle_request(
        agent, {"id": "1", "method": "session/new", "params": {}}
    )  # type: ignore[arg-type]
    assert "result" in response
    assert "session_id" in response["result"]


@pytest.mark.asyncio
async def test_acp_session_prompt(capsys: pytest.CaptureFixture[str]) -> None:
    """session/prompt returns stop_reason and text."""
    client = AcpClient()
    agent = MockAgent()
    new_resp = await client._handle_request(
        agent, {"id": "1", "method": "session/new", "params": {}}
    )  # type: ignore[arg-type]
    session_id = new_resp["result"]["session_id"]

    prompt_resp = await client._handle_request(  # type: ignore[arg-type]
        agent,
        {
            "id": "2",
            "method": "session/prompt",
            "params": {"session_id": session_id, "prompt": "hello"},
        },
    )
    assert "result" in prompt_resp
    assert "stop_reason" in prompt_resp["result"]
    assert "text" in prompt_resp["result"]


@pytest.mark.asyncio
async def test_acp_session_cancel() -> None:
    """session/cancel returns ok."""
    client = AcpClient()
    agent = MockAgent()
    new_resp = await client._handle_request(
        agent, {"id": "1", "method": "session/new", "params": {}}
    )  # type: ignore[arg-type]
    session_id = new_resp["result"]["session_id"]

    cancel_resp = await client._handle_request(  # type: ignore[arg-type]
        agent,
        {"id": "2", "method": "session/cancel", "params": {"session_id": session_id}},
    )
    assert cancel_resp.get("result") == {"ok": True}


@pytest.mark.asyncio
async def test_acp_session_save_and_load() -> None:
    """session/save exports data; session/load restores session."""
    client = AcpClient()
    agent = MockAgent()
    new_resp = await client._handle_request(
        agent, {"id": "1", "method": "session/new", "params": {}}
    )  # type: ignore[arg-type]
    session_id = new_resp["result"]["session_id"]

    save_resp = await client._handle_request(  # type: ignore[arg-type]
        agent,
        {"id": "2", "method": "session/save", "params": {"session_id": session_id}},
    )
    data = save_resp["result"]
    assert isinstance(data, dict)
    assert data.get("id") == session_id

    load_resp = await client._handle_request(  # type: ignore[arg-type]
        agent,
        {"id": "3", "method": "session/load", "params": {"data": data}},
    )
    assert "session_id" in load_resp["result"]


@pytest.mark.asyncio
async def test_acp_unknown_method_returns_error() -> None:
    """Unknown method returns an error response."""
    client = AcpClient()
    agent = MockAgent()
    response = await client._handle_request(agent, {"id": "x", "method": "no/such", "params": {}})  # type: ignore[arg-type]
    assert "error" in response


@pytest.mark.asyncio
async def test_acp_unknown_session_id_returns_error() -> None:
    """session/prompt with unknown session_id returns error."""
    client = AcpClient()
    agent = MockAgent()
    response = await client._handle_request(  # type: ignore[arg-type]
        agent,
        {"id": "1", "method": "session/prompt", "params": {"session_id": "bad", "prompt": "hi"}},
    )
    assert "error" in response


@pytest.mark.asyncio
async def test_acp_run_processes_messages(capsys: pytest.CaptureFixture[str]) -> None:
    """AcpClient.run reads JSON lines and writes responses."""
    client = AcpClient()
    agent = MockAgent()

    # Simulate: one session/new request, then EOF
    lines = [b'{"id":"1","method":"session/new","params":{}}\n']
    reader_mock = AsyncMock()
    reader_mock.readline = AsyncMock(side_effect=lines + [b""])

    mock_protocol = MagicMock()

    async def fake_connect_read_pipe(factory: object, pipe: object) -> None:
        pass

    with patch("asyncio.get_running_loop") as mock_loop:
        loop = MagicMock()
        loop.connect_read_pipe = AsyncMock(side_effect=fake_connect_read_pipe)
        mock_loop.return_value = loop

        with patch("asyncio.StreamReader", return_value=reader_mock):
            with patch("asyncio.StreamReaderProtocol", return_value=mock_protocol):
                await client.run(agent)  # type: ignore[arg-type]

    out = capsys.readouterr().out
    lines_out = [ln for ln in out.strip().splitlines() if ln]
    assert len(lines_out) >= 1
    msg = json.loads(lines_out[0])
    assert msg.get("id") == "1"
    assert "result" in msg
