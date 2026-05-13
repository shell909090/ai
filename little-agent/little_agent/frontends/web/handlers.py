"""WebSocket message handlers: one function per session/* message type."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any

from aiohttp import web

if TYPE_CHECKING:
    from little_agent.types import Agent, Session

    from .client import WebClient

logger = logging.getLogger(__name__)

# Type alias for handler functions.
_Handler = Callable[
    ["WebClient", "Agent", web.WebSocketResponse, dict[str, Any]],
    Coroutine[Any, Any, dict[str, Any] | None],
]


async def _save_after_compress(
    client: WebClient, session: Session, task: asyncio.Task[Any]
) -> None:
    """Wait for a compress task then re-save the session."""
    try:
        await task
    except Exception:
        logger.exception("post-turn compress task failed for session %s", session.id)
    await client.store.auto_save(session)


async def do_session_new(
    client: WebClient, agent: Agent, ws: web.WebSocketResponse, msg: dict[str, Any]
) -> dict[str, Any]:
    """Create session and subscribe ws."""
    session = await agent.new(cwd=None)
    session_id: str = session.id
    client.store.register_session(session_id, session)
    client._active[ws] = session_id
    await client.store.auto_save(session)
    return {"type": "session/new_response", "session_id": session_id}


async def do_session_prompt(
    client: WebClient, agent: Agent, ws: web.WebSocketResponse, msg: dict[str, Any]
) -> dict[str, Any]:
    """Run one prompt turn and auto-save."""
    from .client import _is_valid_session_id

    session_id: str = msg.get("session_id", "")
    if not _is_valid_session_id(session_id):
        return {"error": "Invalid session"}
    sess = client.store.get_session(session_id)
    if sess is None:
        return {"error": "Unknown session"}
    prompt = msg.get("prompt", "")
    if not isinstance(prompt, str):
        return {"error": "prompt must be a string"}
    stop_reason, text = await sess.prompt(prompt)
    await client.store.auto_save(sess)
    compress_task = getattr(sess, "compress_task", None)
    if compress_task is not None:
        t = asyncio.create_task(_save_after_compress(client, sess, compress_task))
        client._bg_tasks.add(t)
        t.add_done_callback(client._bg_tasks.discard)
    return {
        "type": "session/prompt_response",
        "session_id": session_id,
        "stop_reason": stop_reason,
        "text": text,
    }


async def do_session_cancel(
    client: WebClient, agent: Agent, ws: web.WebSocketResponse, msg: dict[str, Any]
) -> dict[str, Any]:
    """Cancel an active turn."""
    from .client import _is_valid_session_id

    session_id: str = msg.get("session_id", "")
    if not _is_valid_session_id(session_id):
        return {"error": "Invalid session"}
    sess = client.store.get_session(session_id)
    if sess is None:
        return {"error": "Unknown session"}
    await sess.cancel()
    return {"type": "session/cancel_response", "ok": True}


async def do_session_list(
    client: WebClient, agent: Agent, ws: web.WebSocketResponse, msg: dict[str, Any]
) -> dict[str, Any]:
    """List all sessions (memory + disk)."""
    sessions = await client.store.list_sessions()
    return {"type": "session/list_response", "sessions": sessions}


async def do_session_resume(
    client: WebClient, agent: Agent, ws: web.WebSocketResponse, msg: dict[str, Any]
) -> None:
    """Load session and push history directly to ws."""
    from .client import _is_valid_session_id

    session_id: str = msg.get("session_id", "")
    if not _is_valid_session_id(session_id):
        await ws.send_json({"error": "Invalid session"})
        return
    sess = await client.store.resume_session(agent, session_id)
    if sess is None:
        await ws.send_json({"error": "Session not found"})
        return
    client.store.register_session(session_id, sess)
    client._active[ws] = session_id
    history = await client.store.read_history(session_id)
    await ws.send_json({"type": "session/resume_response", "session_id": session_id})
    await ws.send_json({"type": "session/history", "session_id": session_id, "nodes": history})


async def do_session_fork(
    client: WebClient, agent: Agent, ws: web.WebSocketResponse, msg: dict[str, Any]
) -> dict[str, Any]:
    """Fork session and subscribe ws to the new session."""
    from .client import _is_valid_session_id

    session_id: str = msg.get("session_id", "")
    if not _is_valid_session_id(session_id):
        return {"error": "Invalid session"}
    sess = client.store.get_session(session_id)
    if sess is None:
        return {"error": "Unknown session"}
    new_sess = await sess.fork()
    new_id: str = new_sess.id
    client.store.register_session(new_id, new_sess)
    client._active[ws] = new_id
    await client.store.auto_save(new_sess)
    return {"type": "session/fork_response", "session_id": new_id}


async def do_session_delete(
    client: WebClient, agent: Agent, ws: web.WebSocketResponse, msg: dict[str, Any]
) -> dict[str, Any]:
    """Delete session and unsubscribe all watchers."""
    from .client import _is_valid_session_id

    session_id: str = msg.get("session_id", "")
    if not _is_valid_session_id(session_id):
        return {"error": "Invalid session"}
    await client.store.delete_session(session_id)
    for conn_ws in list(client._active):
        if client._active[conn_ws] == session_id:
            client._active[conn_ws] = None
    return {"type": "session/delete_response", "session_id": session_id}


async def do_session_compact(
    client: WebClient, agent: Agent, ws: web.WebSocketResponse, msg: dict[str, Any]
) -> dict[str, Any]:
    """Manually trigger history compression for a session."""
    from .client import _is_valid_session_id

    session_id: str = msg.get("session_id", "")
    if not _is_valid_session_id(session_id):
        return {"error": "Invalid session"}
    sess = client.store.get_session(session_id)
    if sess is None:
        return {"error": "Unknown session"}
    try:
        await sess.compress()
    except Exception as exc:
        return {"type": "session/compact_response", "ok": False, "error": str(exc)}
    await client.store.auto_save(sess)
    return {"type": "session/compact_response", "ok": True}


async def do_tools_list(
    client: WebClient, agent: Agent, ws: web.WebSocketResponse, msg: dict[str, Any]
) -> dict[str, Any]:
    """Return the list of registered tools."""
    tools = agent.tools.desc_tool()
    return {
        "type": "tools/list_response",
        "tools": [{"name": name, "desc": td.desc} for name, td in tools.items()],
    }


_DISPATCH: dict[str, _Handler] = {
    "session/new": do_session_new,
    "session/prompt": do_session_prompt,
    "session/cancel": do_session_cancel,
    "session/list": do_session_list,
    "session/fork": do_session_fork,
    "session/delete": do_session_delete,
    "session/compact": do_session_compact,
    "tools/list": do_tools_list,
}


async def dispatch_message(
    client: WebClient, agent: Agent, ws: web.WebSocketResponse, msg: dict[str, Any]
) -> dict[str, Any] | None:
    """Route a client message to the appropriate handler."""
    msg_type = msg.get("type", "")
    try:
        if msg_type == "session/resume":
            await do_session_resume(client, agent, ws, msg)
            return None
        handler = _DISPATCH.get(msg_type)
        if handler is None:
            return {"error": f"Unknown message type: {msg_type}"}
        return await handler(client, agent, ws, msg)
    except Exception as exc:
        logger.exception("Error handling client message")
        return {"error": str(exc)}
