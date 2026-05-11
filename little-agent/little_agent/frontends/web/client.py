"""WebClient: Client protocol implementation and WebSocket connection management."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aiohttp import web

from little_agent.types import JSONValue, SessionUpdate

from ..protocol import Client
from .store import SessionStore

if TYPE_CHECKING:
    from little_agent.agent.protocol import Agent, Session

logger = logging.getLogger(__name__)

_UUID4_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


def _is_valid_session_id(session_id: str) -> bool:
    """Return True only for canonical UUID v4 strings."""
    return bool(_UUID4_RE.match(session_id))


class WebClient(Client):
    """Web client that pushes updates via WebSocket and handles permission requests."""

    def __init__(self, sessions_dir: Path | None = None) -> None:
        self.store = SessionStore(sessions_dir)
        self._websockets: set[web.WebSocketResponse] = set()
        self._permission_futures: dict[str, asyncio.Future[bool]] = {}
        self._active: dict[web.WebSocketResponse, str | None] = {}
        self._ws_locks: dict[web.WebSocketResponse, asyncio.Lock] = {}
        # Holds strong references to background tasks to prevent GC under Python 3.11+.
        self._bg_tasks: set[asyncio.Task[object]] = set()

    async def update(self, session: Session, update: SessionUpdate) -> None:
        """Send update to WebSocket clients subscribed to this session."""
        session_id = getattr(session, "id", None)
        message = {
            "type": "session/update",
            "session_id": session_id,
            "update": {"type": update.type, "data": update.data},
        }
        await self._send_to_session(session_id, message)

    async def request_permission(
        self,
        session: Session,
        kind: str,
        payload: dict[str, JSONValue],
    ) -> bool:
        """Send permission request via WebSocket and wait for response."""
        logger.debug("Permission request: kind=%s payload=%s", kind, payload)
        session_id = getattr(session, "id", None)
        req_id = f"perm_{session_id}_{kind}_{id(payload)}"

        message = {
            "type": "session/request_permission",
            "id": req_id,
            "session_id": session_id,
            "kind": kind,
            "payload": payload,
        }
        await self._send_to_session(session_id, message)

        try:
            return await asyncio.wait_for(
                self._wait_permission_response(req_id),
                timeout=60.0,
            )
        except TimeoutError:
            logger.warning("Permission request timed out: %s", req_id)
            return False

    async def _wait_permission_response(self, req_id: str) -> bool:
        """Wait for a permission response matching req_id."""
        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()
        self._permission_futures[req_id] = future
        try:
            return await future
        finally:
            self._permission_futures.pop(req_id, None)

    def _handle_permission_response(self, msg: dict[str, Any]) -> None:
        """Resolve a pending permission future from a response message."""
        req_id = msg.get("id", "")
        future = self._permission_futures.get(req_id)
        if future is None or future.done():
            return
        granted = bool(msg.get("granted", False))
        future.set_result(granted)

    async def _send_to_session(self, session_id: str | None, message: dict[str, Any]) -> None:
        """Send a JSON message to all WebSocket connections subscribed to session_id."""
        data = json.dumps(message, ensure_ascii=False)
        dead: set[web.WebSocketResponse] = set()
        for ws, active_id in list(self._active.items()):
            if active_id != session_id:
                continue
            lock = self._ws_locks.get(ws)
            if lock is None:
                dead.add(ws)
                continue
            try:
                async with lock:
                    await ws.send_str(data)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._active.pop(ws, None)
            self._websockets.discard(ws)
            self._ws_locks.pop(ws, None)

    def add_websocket(self, ws: web.WebSocketResponse) -> None:
        """Register a new WebSocket connection."""
        self._websockets.add(ws)
        self._ws_locks[ws] = asyncio.Lock()

    def remove_websocket(self, ws: web.WebSocketResponse) -> None:
        """Unregister a WebSocket connection."""
        self._websockets.discard(ws)
        self._ws_locks.pop(ws, None)

    @property
    def _sessions(self) -> OrderedDict[str, Session]:
        """Compatibility accessor for tests; delegates to store._sessions."""
        return self.store._sessions

    async def handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        """Handle a WebSocket connection (delegates to server module)."""
        from .server import handle_websocket as _handle

        return await _handle(request)

    async def run(self, agent: Agent, host: str = "127.0.0.1", port: int = 8080) -> None:
        """Run the web server."""
        from .server import run as _run

        await _run(self, agent, host=host, port=port)
