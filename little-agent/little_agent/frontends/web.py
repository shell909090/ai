"""Web frontend implementation using aiohttp HTTP + WebSocket."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aiohttp import WSMsgType, web

from little_agent.types import JSONValue, SessionUpdate

from .protocol import Client

if TYPE_CHECKING:
    from little_agent.agent.protocol import Agent, Session

logger = logging.getLogger(__name__)

AGENT_KEY: web.AppKey[Agent] = web.AppKey("agent")
CLIENT_KEY: web.AppKey[WebClient] = web.AppKey("client")


class WebClient(Client):
    """Web client that pushes updates via WebSocket and handles permission requests."""

    def __init__(self) -> None:
        self._websockets: set[web.WebSocketResponse] = set()
        self._permission_futures: dict[str, asyncio.Future[bool]] = {}

    async def update(self, session: Session, update: SessionUpdate) -> None:
        """Broadcast update to all connected WebSocket clients."""
        session_id = getattr(session, "id", None)
        message = {
            "type": "session/update",
            "session_id": session_id,
            "update": {"type": update.type, "data": update.data},
        }
        await self._broadcast(message)

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
        await self._broadcast(message)

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

    async def _broadcast(self, message: dict[str, Any]) -> None:
        """Send a JSON message to all connected WebSockets."""
        data = json.dumps(message, ensure_ascii=False)
        dead: set[web.WebSocketResponse] = set()
        for ws in self._websockets:
            try:
                await ws.send_str(data)
            except Exception:
                dead.add(ws)
        self._websockets -= dead

    def add_websocket(self, ws: web.WebSocketResponse) -> None:
        """Register a new WebSocket connection."""
        self._websockets.add(ws)

    def remove_websocket(self, ws: web.WebSocketResponse) -> None:
        """Unregister a WebSocket connection."""
        self._websockets.discard(ws)

    async def handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        """Handle a WebSocket connection."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.add_websocket(ws)
        logger.info("WebSocket connected")

        sessions: dict[str, Session] = {}

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                    except json.JSONDecodeError:
                        await ws.send_json({"error": "Invalid JSON"})
                        continue

                    if not isinstance(data, dict):
                        await ws.send_json({"error": "Expected JSON object"})
                        continue

                    msg_type = data.get("type", "")
                    if msg_type == "session/permission_response":
                        self._handle_permission_response(data)
                        continue

                    # Handle other client messages via agent
                    agent = request.app[AGENT_KEY]
                    response = await self._handle_client_message(agent, data, sessions)
                    await ws.send_json(response)
                elif msg.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
                    break
        finally:
            self.remove_websocket(ws)
            logger.info("WebSocket disconnected")

        return ws

    async def _handle_client_message(
        self, agent: Agent, msg: dict[str, Any], sessions: dict[str, Session]
    ) -> dict[str, Any]:
        """Dispatch client messages to the agent."""
        msg_type = msg.get("type", "")
        try:
            match msg_type:
                case "session/new":
                    cwd = msg.get("cwd")
                    session = await agent.new(cwd=cwd)
                    session_id: str = getattr(session, "id", "")
                    sessions[session_id] = session
                    return {
                        "type": "session/new_response",
                        "session_id": session_id,
                    }
                case "session/prompt":
                    session_id = msg.get("session_id", "")
                    sess = sessions.get(session_id)
                    if sess is None:
                        return {"error": f"Unknown session: {session_id}"}
                    prompt = msg.get("prompt", "")
                    if not isinstance(prompt, str):
                        return {"error": "prompt must be a string"}
                    stop_reason, text = await sess.prompt(prompt)
                    return {
                        "type": "session/prompt_response",
                        "session_id": session_id,
                        "stop_reason": stop_reason,
                        "text": text,
                    }
                case "session/cancel":
                    session_id = msg.get("session_id", "")
                    sess = sessions.get(session_id)
                    if sess is None:
                        return {"error": f"Unknown session: {session_id}"}
                    await sess.cancel()
                    return {"type": "session/cancel_response", "ok": True}
                case _:
                    return {"error": f"Unknown message type: {msg_type}"}
        except Exception as exc:
            logger.exception("Error handling client message")
            return {"error": str(exc)}

    async def run(self, agent: Agent, host: str = "127.0.0.1", port: int = 8080) -> None:
        """Run the web server."""
        app = web.Application()
        app[AGENT_KEY] = agent
        app[CLIENT_KEY] = self

        static_dir = Path(__file__).parent / "static"
        if static_dir.exists():
            app.router.add_static("/", static_dir, name="static")

        app.router.add_get("/ws", self.handle_websocket)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()
        logger.info("Web server started on http://%s:%d", host, port)

        # Keep running until cancelled
        try:
            while True:
                await asyncio.sleep(3600)
        finally:
            await runner.cleanup()
