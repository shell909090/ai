"""Web frontend implementation using aiohttp HTTP + WebSocket."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
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

    def __init__(self, sessions_dir: Path | None = None) -> None:
        self._websockets: set[web.WebSocketResponse] = set()
        self._permission_futures: dict[str, asyncio.Future[bool]] = {}
        self._sessions: dict[str, Session] = {}
        self._active: dict[web.WebSocketResponse, str | None] = {}
        self._sessions_dir: Path | None = sessions_dir  # None disables persistence

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
            try:
                await ws.send_str(data)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._active.pop(ws, None)
            self._websockets.discard(ws)

    def add_websocket(self, ws: web.WebSocketResponse) -> None:
        """Register a new WebSocket connection."""
        self._websockets.add(ws)

    def remove_websocket(self, ws: web.WebSocketResponse) -> None:
        """Unregister a WebSocket connection."""
        self._websockets.discard(ws)

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    async def _auto_save(self, session: Session) -> None:
        """Write session.save() as JSON to {sessions_dir}/{session_id}.json."""
        if self._sessions_dir is None:
            return
        try:
            session_id = session.id
            path = self._sessions_dir / f"{session_id}.json"
            data = json.dumps(session.save(), ensure_ascii=False)
            await asyncio.to_thread(self._sync_write_text, path, data)
        except Exception:
            logger.exception("Failed to auto-save session %s", getattr(session, "id", "?"))

    def _sync_write_text(self, path: Path, text: str) -> None:
        """Write text to path, creating parent dirs; called via asyncio.to_thread."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _read_preview(self, session_id: str) -> str:
        """Read first user_prompt record from JSONL and return its prompt (max 50 chars)."""
        if self._sessions_dir is None:
            return ""
        path = self._sessions_dir / f"session_{session_id}.jsonl"
        if not path.exists():
            return ""
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        if record.get("kind") == "user_prompt":
                            prompt = record.get("prompt", "")
                            if isinstance(prompt, str):
                                return prompt[:50]
                    except json.JSONDecodeError:
                        pass
        except OSError:
            logger.exception("Failed to read preview for session %s", session_id)
        return ""

    async def _list_sessions(self) -> list[dict[str, Any]]:
        """List sessions from disk and memory, sorted by updated_at descending."""
        if self._sessions_dir is not None:
            result = await asyncio.to_thread(self._sync_scan_sessions_dir)
        else:
            result = {}
        for sid in self._sessions:
            if sid not in result:
                result[sid] = {
                    "id": sid,
                    "updated_at": datetime.now(UTC).isoformat(),
                    "preview": "",
                }
        return sorted(result.values(), key=lambda x: x["updated_at"], reverse=True)

    def _sync_scan_sessions_dir(self) -> dict[str, dict[str, Any]]:
        """Scan sessions_dir for .json files; called via asyncio.to_thread."""
        result: dict[str, dict[str, Any]] = {}
        if self._sessions_dir is None or not self._sessions_dir.exists():
            return result
        for json_path in self._sessions_dir.glob("*.json"):
            try:
                raw = json.loads(json_path.read_text(encoding="utf-8"))
                sid = raw.get("id")
                if not isinstance(sid, str):
                    continue
                mtime = json_path.stat().st_mtime
                updated_at = datetime.fromtimestamp(mtime, tz=UTC).isoformat()
                preview = self._read_preview(sid)
                result[sid] = {"id": sid, "updated_at": updated_at, "preview": preview}
            except Exception:
                logger.exception("Failed to read session file %s", json_path)
        return result

    async def _resume_session(self, agent: Agent, session_id: str) -> Session | None:
        """Return session from memory or load from disk JSON. None if not found."""
        if session_id in self._sessions:
            return self._sessions[session_id]
        if self._sessions_dir is None:
            return None
        path = self._sessions_dir / f"{session_id}.json"
        if not path.exists():
            return None
        try:
            text = await asyncio.to_thread(path.read_text, "utf-8")
            data: JSONValue = json.loads(text)
            return await agent.load(data)
        except Exception:
            logger.exception("Failed to load session %s from disk", session_id)
            return None

    async def _read_history(self, session_id: str) -> list[dict[str, Any]]:
        """Read JSONL history for session_id, stripping the session_id key."""
        if self._sessions_dir is None:
            return []
        path = self._sessions_dir / f"session_{session_id}.jsonl"
        if not path.exists():
            return []
        return await asyncio.to_thread(self._sync_read_history, path)

    def _sync_read_history(self, path: Path) -> list[dict[str, Any]]:
        """Read and parse a JSONL history file; called via asyncio.to_thread."""
        records: list[dict[str, Any]] = []
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record: dict[str, Any] = json.loads(line)
                        record.pop("session_id", None)
                        records.append(record)
                    except json.JSONDecodeError:
                        pass
        except OSError:
            logger.exception("Failed to read history file %s", path)
        return records

    async def _delete_session(self, session_id: str) -> None:
        """Remove session from memory and delete both disk files."""
        self._sessions.pop(session_id, None)
        if self._sessions_dir is None:
            return
        json_path = self._sessions_dir / f"{session_id}.json"
        jsonl_path = self._sessions_dir / f"session_{session_id}.jsonl"
        await asyncio.to_thread(self._sync_delete_files, json_path, jsonl_path)

    def _sync_delete_files(self, *paths: Path) -> None:
        """Unlink files, ignoring missing; called via asyncio.to_thread."""
        for p in paths:
            try:
                p.unlink(missing_ok=True)
            except Exception:
                logger.exception("Failed to delete %s", p)

    # ------------------------------------------------------------------
    # WebSocket handler
    # ------------------------------------------------------------------

    async def handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        """Handle a WebSocket connection."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.add_websocket(ws)
        self._active[ws] = None
        logger.info("WebSocket connected")

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
                    response = await self._handle_client_message(agent, ws, data)
                    if response is not None:
                        await ws.send_json(response)
                elif msg.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
                    break
        finally:
            self._active.pop(ws, None)
            self.remove_websocket(ws)
            logger.info("WebSocket disconnected")

        return ws

    async def _handle_client_message(
        self, agent: Agent, ws: web.WebSocketResponse, msg: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Dispatch client messages to the agent."""
        msg_type = msg.get("type", "")
        try:
            match msg_type:
                case "session/new":
                    return await self._do_session_new(agent, ws, msg)
                case "session/prompt":
                    return await self._do_session_prompt(msg)
                case "session/cancel":
                    return await self._do_session_cancel(msg)
                case "session/list":
                    return await self._do_session_list()
                case "session/resume":
                    await self._do_session_resume(agent, ws, msg)
                    return None
                case "session/fork":
                    return await self._do_session_fork(ws, msg)
                case "session/delete":
                    return await self._do_session_delete(msg)
                case _:
                    return {"error": f"Unknown message type: {msg_type}"}
        except Exception as exc:
            logger.exception("Error handling client message")
            return {"error": str(exc)}

    async def _do_session_new(
        self, agent: Agent, ws: web.WebSocketResponse, msg: dict[str, Any]
    ) -> dict[str, Any]:
        """Create session and subscribe ws."""
        cwd = msg.get("cwd")
        session = await agent.new(cwd=cwd)
        session_id: str = session.id
        self._sessions[session_id] = session
        self._active[ws] = session_id
        await self._auto_save(session)
        return {"type": "session/new_response", "session_id": session_id}

    async def _do_session_prompt(self, msg: dict[str, Any]) -> dict[str, Any]:
        """Run one prompt turn and auto-save."""
        session_id: str = msg.get("session_id", "")
        sess = self._sessions.get(session_id)
        if sess is None:
            return {"error": f"Unknown session: {session_id}"}
        prompt = msg.get("prompt", "")
        if not isinstance(prompt, str):
            return {"error": "prompt must be a string"}
        stop_reason, text = await sess.prompt(prompt)
        await self._auto_save(sess)
        return {
            "type": "session/prompt_response",
            "session_id": session_id,
            "stop_reason": stop_reason,
            "text": text,
        }

    async def _do_session_cancel(self, msg: dict[str, Any]) -> dict[str, Any]:
        """Cancel an active turn."""
        session_id: str = msg.get("session_id", "")
        sess = self._sessions.get(session_id)
        if sess is None:
            return {"error": f"Unknown session: {session_id}"}
        await sess.cancel()
        return {"type": "session/cancel_response", "ok": True}

    async def _do_session_list(self) -> dict[str, Any]:
        """List all sessions (memory + disk)."""
        sessions = await self._list_sessions()
        return {"type": "session/list_response", "sessions": sessions}

    async def _do_session_resume(
        self, agent: Agent, ws: web.WebSocketResponse, msg: dict[str, Any]
    ) -> None:
        """Load session and push history directly to ws; returns None."""
        session_id: str = msg.get("session_id", "")
        sess = await self._resume_session(agent, session_id)
        if sess is None:
            await ws.send_json({"error": f"Session not found: {session_id}"})
            return None
        self._sessions[session_id] = sess
        self._active[ws] = session_id
        history = await self._read_history(session_id)
        await ws.send_json({"type": "session/resume_response", "session_id": session_id})
        await ws.send_json({"type": "session/history", "session_id": session_id, "nodes": history})
        return None

    async def _do_session_fork(
        self, ws: web.WebSocketResponse, msg: dict[str, Any]
    ) -> dict[str, Any]:
        """Fork session and subscribe ws to the new session."""
        session_id: str = msg.get("session_id", "")
        sess = self._sessions.get(session_id)
        if sess is None:
            return {"error": f"Unknown session: {session_id}"}
        new_sess = await sess.fork()
        new_id: str = new_sess.id
        self._sessions[new_id] = new_sess
        self._active[ws] = new_id
        await self._auto_save(new_sess)
        return {"type": "session/fork_response", "session_id": new_id}

    async def _do_session_delete(self, msg: dict[str, Any]) -> dict[str, Any]:
        """Delete session and unsubscribe all watchers."""
        session_id: str = msg.get("session_id", "")
        await self._delete_session(session_id)
        for conn_ws in list(self._active):
            if self._active[conn_ws] == session_id:
                self._active[conn_ws] = None
        return {"type": "session/delete_response", "session_id": session_id}

    async def run(self, agent: Agent, host: str = "127.0.0.1", port: int = 8080) -> None:
        """Run the web server."""
        if self._sessions_dir is not None:
            from little_agent.agent.logger import FileLogger

            template = str(self._sessions_dir / "session_{session_id}.jsonl")
            if not any(getattr(lg, "_template", None) == template for lg in agent.loggers):
                agent.loggers.append(FileLogger(template))
            self._sessions_dir.mkdir(parents=True, exist_ok=True)

        app = web.Application()
        app[AGENT_KEY] = agent
        app[CLIENT_KEY] = self

        async def _add_csp_header(request: web.Request, response: web.StreamResponse) -> None:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; "
                "style-src 'self' 'unsafe-inline'; connect-src 'self' ws: wss:"
            )

        app.on_response_prepare.append(_add_csp_header)

        static_dir = Path(__file__).parent / "static"
        if static_dir.exists():
            index = static_dir / "index.html"

            async def _serve_index(request: web.Request) -> web.StreamResponse:
                return web.FileResponse(index)

            app.router.add_get("/", _serve_index)
            app.router.add_static("/", static_dir, name="static")
        else:
            logger.warning("Static directory not found: %s", static_dir)

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
