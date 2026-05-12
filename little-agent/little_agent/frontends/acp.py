"""ACP (Agent Communication Protocol) frontend over stdin/stdout."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import TYPE_CHECKING, Any

from little_agent.types import JSONValue, SessionUpdate

from .protocol import Client

if TYPE_CHECKING:
    from little_agent.agent.protocol import Agent, Session

logger = logging.getLogger(__name__)


class AcpClient(Client):
    """ACP frontend that communicates via newline-delimited JSON on stdin/stdout."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._permission_futures: dict[str, asyncio.Future[bool]] = {}
        self._stdout_lock = asyncio.Lock()

    async def _write_json(self, obj: dict[str, Any]) -> None:
        """Write a JSON object as a single line to stdout, protected by a lock."""
        data = json.dumps(obj, ensure_ascii=False) + "\n"
        async with self._stdout_lock:
            sys.stdout.write(data)
            sys.stdout.flush()

    async def update(self, session: Session, update: SessionUpdate) -> None:
        """Forward session updates as ACP session/update notifications."""
        session_id = getattr(session, "id", None)
        await self._write_json(
            {
                "method": "session/update",
                "params": {
                    "sessionId": session_id,
                    "update": self._to_acp_update(update),
                },
            }
        )

    @staticmethod
    def _to_acp_update(update: SessionUpdate) -> dict[str, Any]:
        """Convert a SessionUpdate to ACP update payload."""
        if update.type in ("agent_message_chunk", "thinking_chunk"):
            return {
                "sessionUpdate": update.type,
                "content": {"text": update.data.get("text", "")},
            }
        if update.type == "tool_call":
            calls = update.data.get("calls", {})
            if calls and isinstance(calls, dict):
                first_call = next(iter(calls.values()))
                tool_name = (
                    first_call.get("tool_name", "tool") if isinstance(first_call, dict) else "tool"
                )
                n = len(calls)
                title = tool_name if n == 1 else f"{tool_name} (+{n - 1} more)"
            else:
                title = "tool"
            return {"sessionUpdate": "tool_call", "title": title, "kind": "tool_call"}
        # tool_call_update and other types: pass through
        return {"sessionUpdate": update.type, **update.data}

    async def request_permission(
        self,
        session: Session,
        kind: str,
        payload: dict[str, JSONValue],
    ) -> bool:
        """Send permission request via ACP JSON-RPC and wait for response."""
        logger.debug("Permission request: kind=%s payload=%s", kind, payload)
        session_id = getattr(session, "id", None)
        req_id = f"perm_{session_id}_{kind}_{id(payload)}"

        await self._write_json(
            {
                "id": req_id,
                "method": "session/request_permission",
                "params": {
                    "sessionId": session_id,
                    "toolCall": {"toolCallId": kind},
                    "options": [
                        {"optionId": "allow-once", "kind": "allow-once", "name": "Allow once"},
                        {"optionId": "deny", "kind": "deny", "name": "Deny"},
                    ],
                    "payload": payload,
                },
            }
        )

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
        """Look up session by session_id in params (accepts both camelCase and snake_case)."""
        session_id = params.get("sessionId") or params.get("session_id", "")
        if not isinstance(session_id, str) or session_id not in self._sessions:
            raise ValueError(f"Unknown session_id: {session_id!r}")
        return self._sessions[session_id]

    async def _dispatch(self, agent: Agent, method: str, params: dict[str, Any]) -> JSONValue:
        """Dispatch ACP method to the appropriate handler."""
        match method:
            case "initialize":
                return {
                    "agentInfo": {"name": "little-agent", "version": "1.0"},
                    "protocolVersion": params.get("protocolVersion", 1),
                }
            case "session/new":
                cwd: str | None = params.get("cwd")
                session = await agent.new(cwd=cwd)
                session_id: str = getattr(session, "id", "")
                self._sessions[session_id] = session
                return {"session_id": session_id, "sessionId": session_id}
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
        if isinstance(prompt, list):
            # Extract text from list of content blocks
            prompt = " ".join(
                block.get("text", "")
                for block in prompt
                if isinstance(block, dict) and block.get("type") == "text"
            ).strip()
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
        return {"session_id": session_id, "sessionId": session_id}

    async def _handle_and_reply(self, agent: Agent, msg: dict[str, Any]) -> None:
        """Process a request as a background task and write the response."""
        try:
            response = await self._handle_request(agent, msg)
            await self._write_json(response)
        except Exception:
            logger.exception("Unhandled error in background prompt task")

    def _handle_jsonrpc_response(self, msg: dict[str, Any]) -> None:
        """Resolve a pending permission future from an incoming JSON-RPC response."""
        req_id = msg.get("id", "")
        future = self._permission_futures.get(req_id)
        if future is None or future.done():
            return
        # Legacy format: {"id": ..., "granted": bool}
        if "granted" in msg:
            granted = bool(msg["granted"])
        else:
            # ACP format: {"id": ..., "result": {"outcome": {"outcome": "selected", ...}}}
            result = msg.get("result", {})
            outcome = result.get("outcome", {}) if isinstance(result, dict) else {}
            granted = isinstance(outcome, dict) and outcome.get("outcome") == "selected"
        future.set_result(granted)

    # Kept for backward compatibility with existing tests
    def _handle_permission_response(self, msg: dict[str, Any]) -> None:
        """Resolve a pending permission future (legacy name)."""
        self._handle_jsonrpc_response(msg)

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
                await self._write_json({"error": f"Invalid JSON: {exc}"})
                continue

            if not isinstance(msg, dict):
                await self._write_json({"error": "Request must be a JSON object"})
                continue

            # JSON-RPC responses to server-initiated requests have "id" but no "method"
            if "id" in msg and "method" not in msg:
                self._handle_jsonrpc_response(msg)
                continue

            # session/prompt is launched as a background task so stdin stays readable
            # while the prompt is running (needed for permission request/response interleaving)
            if msg.get("method") == "session/prompt":
                asyncio.create_task(self._handle_and_reply(agent, msg))
                continue

            response = await self._handle_request(agent, msg)
            await self._write_json(response)
