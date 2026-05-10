"""Tests for web handlers dispatch and individual handler functions."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from little_agent.frontends.web.handlers import dispatch_message


def _make_client(session_id: str = "11111111-1111-4111-8111-111111111111") -> MagicMock:
    """Build a minimal WebClient mock with a store."""
    client = MagicMock()
    client._active = {}
    sess = MagicMock()
    sess.id = session_id
    sess.prompt = AsyncMock(return_value=("end_turn", "answer"))
    sess.cancel = AsyncMock()
    sess.fork = AsyncMock(return_value=MagicMock(id="fork-id"))
    client.store.get_session = MagicMock(return_value=sess)
    client.store.register_session = MagicMock()
    client.store.auto_save = AsyncMock()
    client.store.list_sessions = AsyncMock(return_value=[])
    client.store.resume_session = AsyncMock(return_value=None)
    client.store.read_history = AsyncMock(return_value=[])
    client.store.delete_session = AsyncMock()
    return client


def _make_ws() -> MagicMock:
    ws = MagicMock()
    ws.send_json = AsyncMock()
    return ws


# ---------------------------------------------------------------------------
# dispatch routing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_unknown_type_returns_error() -> None:
    """dispatch_message returns an error dict for unknown message types."""
    client = _make_client()
    agent = MagicMock()
    ws = _make_ws()
    resp = await dispatch_message(client, agent, ws, {"type": "totally/unknown"})
    assert resp is not None
    assert "error" in resp


@pytest.mark.asyncio
async def test_dispatch_session_list() -> None:
    """dispatch_message routes session/list to the list handler."""
    client = _make_client()
    agent = MagicMock()
    ws = _make_ws()
    resp = await dispatch_message(client, agent, ws, {"type": "session/list"})
    assert resp is not None
    assert resp.get("type") == "session/list_response"


@pytest.mark.asyncio
async def test_dispatch_session_new() -> None:
    """dispatch_message routes session/new to the new handler."""
    client = _make_client()
    agent = MagicMock()
    new_sess = MagicMock()
    new_sess.id = "new-id"
    agent.new = AsyncMock(return_value=new_sess)
    ws = _make_ws()
    resp = await dispatch_message(client, agent, ws, {"type": "session/new"})
    assert resp is not None
    assert resp.get("type") == "session/new_response"
    assert resp.get("session_id") == "new-id"


@pytest.mark.asyncio
async def test_dispatch_session_prompt_invalid_id() -> None:
    """session/prompt with a bad session_id returns an error."""
    client = _make_client()
    agent = MagicMock()
    ws = _make_ws()
    resp = await dispatch_message(
        client, agent, ws, {"type": "session/prompt", "session_id": "bad-id"}
    )
    assert resp is not None
    assert "error" in resp


@pytest.mark.asyncio
async def test_dispatch_session_prompt_success() -> None:
    """session/prompt delegates to session.prompt and returns response."""
    sid = "11111111-1111-4111-8111-111111111111"
    client = _make_client(sid)
    agent = MagicMock()
    ws = _make_ws()
    resp = await dispatch_message(
        client, agent, ws, {"type": "session/prompt", "session_id": sid, "prompt": "hi"}
    )
    assert resp is not None
    assert resp.get("type") == "session/prompt_response"
    assert resp.get("text") == "answer"


@pytest.mark.asyncio
async def test_dispatch_session_cancel() -> None:
    """session/cancel calls session.cancel()."""
    sid = "11111111-1111-4111-8111-111111111111"
    client = _make_client(sid)
    agent = MagicMock()
    ws = _make_ws()
    resp = await dispatch_message(client, agent, ws, {"type": "session/cancel", "session_id": sid})
    assert resp is not None
    assert resp.get("type") == "session/cancel_response"
    client.store.get_session.return_value.cancel.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_session_delete() -> None:
    """session/delete calls store.delete_session."""
    sid = "11111111-1111-4111-8111-111111111111"
    client = _make_client(sid)
    agent = MagicMock()
    ws = _make_ws()
    resp = await dispatch_message(client, agent, ws, {"type": "session/delete", "session_id": sid})
    assert resp is not None
    assert resp.get("type") == "session/delete_response"
    client.store.delete_session.assert_awaited_once_with(sid)


@pytest.mark.asyncio
async def test_dispatch_session_resume_not_found() -> None:
    """session/resume sends error when session not found."""
    client = _make_client()
    agent = MagicMock()
    ws = _make_ws()
    sid = "11111111-1111-4111-8111-111111111111"
    resp = await dispatch_message(client, agent, ws, {"type": "session/resume", "session_id": sid})
    # resume sends directly to ws, returns None
    assert resp is None
    ws.send_json.assert_called()
    call_arg = ws.send_json.call_args[0][0]
    assert "error" in call_arg


@pytest.mark.asyncio
async def test_dispatch_handler_exception_returns_error() -> None:
    """An exception in a handler is caught and returned as an error dict."""
    client = _make_client()
    agent = MagicMock()
    ws = _make_ws()
    client.store.list_sessions = AsyncMock(side_effect=RuntimeError("boom"))
    resp = await dispatch_message(client, agent, ws, {"type": "session/list"})
    assert resp is not None
    assert "error" in resp
