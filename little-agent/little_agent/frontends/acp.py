"""ACP (Agent Communication Protocol) frontend over stdin/stdout."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import TYPE_CHECKING, Any

from little_agent.types import JSONValue

from .protocol import Client, SessionUpdate

if TYPE_CHECKING:
    from little_agent.agent.protocol import Agent, Session

logger = logging.getLogger(__name__)


def _write_json(obj: dict[str, Any]) -> None:
    """Write a JSON object as a single line to stdout."""
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


class AcpClient(Client):
    """ACP frontend that communicates via newline-delimited JSON on stdin/stdout."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._permission_futures: dict[str, asyncio.Future[bool]] = {}

    async def update(self, session: Session, update: SessionUpdate) -> None:
        """Forward session updates to stdout as JSON."""
        session_id = getattr(session, "id", None)
        _write_json(
            {
                "type": "session/update",
                "session_id": session_id,
                "update": {"type": update.type, "data": update.data},
            }
        )

    async def request_permission(
        self,
        session: Session,
        kind: str,
        payload: dict[str, JSONValue],
    ) -> bool:
        """Send permission request via ACP and wait for response."""
        logger.debug("Permission request: kind=%s payload=%s", kind, payload)
        session_id = getattr(session, "id", None)
        req_id = f"perm_{session_id}_{kind}_{id(payload)}"

        _write_json(
            {
                "type": "session/request_permission",
                "id": req_id,
                "session_id": session_id,
                "kind": kind,
                "payload": payload,
            }
        )

        # Wait for response with a timeout
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
        # ACP client reads from stdin in run(); we need a way to receive
        # responses. For simplicity, store a future and have run() resolve it.
        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()
        self._permission_futures[req_id] = future
        try:
            return await future
        finally:
            self._permission_futures.pop(req_id, None)

    async def _handle_request(self, agent: Agent, msg: dict[str, Any]) -> dict[str, Any]:
        """Dispatch a single ACP request and return a response dict."""
        req_id = msg.get("id")
        method = msg.get("method", "")
        params: dict[str, Any] = msg.get("params") or {}

        try:
            result = await self._dispatch(agent, method, params)
            return {"id": req_id, "result": result}
        except Exception as exc:
            logger.exception("ACP request error: method=%s", method)
            return {"id": req_id, "error": str(exc)}

    def _get_session(self, params: dict[str, Any]) -> Session:
        """Look up session by session_id in params."""
        session_id = params.get("session_id", "")
        if not isinstance(session_id, str) or session_id not in self._sessions:
            raise ValueError(f"Unknown session_id: {session_id!r}")
        return self._sessions[session_id]

    async def _dispatch(self, agent: Agent, method: str, params: dict[str, Any]) -> JSONValue:
        """Dispatch ACP method to the appropriate handler."""
        match method:
            case "session/new":
                cwd: str | None = params.get("cwd")
                session = await agent.new(cwd=cwd)
                session_id: str = getattr(session, "id", "")
                self._sessions[session_id] = session
                return {"session_id": session_id}
            case "session/prompt":
                return await self._do_prompt(params)
            case "session/cancel":
                await self._get_session(params).cancel()
                return {"ok": True}
            case "session/save":
                return self._get_session(params).save()
            case "session/load":
                return await self._do_load(agent, params)
            case _:
                raise ValueError(f"Unknown method: {method!r}")

    async def _do_prompt(self, params: dict[str, Any]) -> JSONValue:
        """Handle session/prompt method."""
        session = self._get_session(params)
        prompt = params.get("prompt", "")
        if not isinstance(prompt, str):
            raise ValueError("prompt must be a string")
        stop_reason, text = await session.prompt(prompt)
        return {"stop_reason": stop_reason, "text": text}

    async def _do_load(self, agent: Agent, params: dict[str, Any]) -> JSONValue:
        """Handle session/load method."""
        data = params.get("data")
        if not isinstance(data, dict):
            raise ValueError("session/load requires 'data' dict")
        session = await agent.load(data)
        session_id = getattr(session, "id", "")
        self._sessions[session_id] = session
        return {"session_id": session_id}

    async def run(self, agent: Agent) -> None:
        """Run the ACP event loop: read JSON requests from stdin, write responses to stdout."""
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)

        while True:
            try:
                line = await reader.readline()
            except Exception:
                break
            if not line:
                break

            line_str = line.decode("utf-8", errors="replace").strip()
            if not line_str:
                continue

            try:
                msg = json.loads(line_str)
            except json.JSONDecodeError as exc:
                _write_json({"error": f"Invalid JSON: {exc}"})
                continue

            if not isinstance(msg, dict):
                _write_json({"error": "Request must be a JSON object"})
                continue

            msg_type = msg.get("type", "")
            if msg_type == "session/permission_response":
                self._handle_permission_response(msg)
                continue

            response = await self._handle_request(agent, msg)
            _write_json(response)

    def _handle_permission_response(self, msg: dict[str, Any]) -> None:
        """Resolve a pending permission future from a response message."""
        req_id = msg.get("id", "")
        future = self._permission_futures.get(req_id)
        if future is None or future.done():
            return
        granted = bool(msg.get("granted", False))
        future.set_result(granted)
