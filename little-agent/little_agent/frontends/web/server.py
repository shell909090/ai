"""aiohttp application builder and server lifecycle."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from aiohttp import WSMsgType, web

if TYPE_CHECKING:
    from little_agent.agent.protocol import Agent

    from .client import WebClient

logger = logging.getLogger(__name__)

AGENT_KEY: web.AppKey[Agent] = web.AppKey("agent")
CLIENT_KEY: web.AppKey[WebClient] = web.AppKey("client")


async def handle_websocket(request: web.Request) -> web.WebSocketResponse:
    """Handle a WebSocket connection."""
    from .handlers import dispatch_message

    client: WebClient = request.app[CLIENT_KEY]
    agent: Agent = request.app[AGENT_KEY]

    origin = request.headers.get("Origin")
    if origin is not None and origin != "null":
        expected = f"{request.url.scheme}://{request.url.authority}"
        if origin != expected:
            raise web.HTTPForbidden(reason="Cross-origin WebSocket not allowed")

    ws = web.WebSocketResponse()
    await ws.prepare(request)
    client.add_websocket(ws)
    client._active[ws] = None
    logger.info("WebSocket connected")

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    import json

                    data = json.loads(msg.data)
                except Exception:
                    await ws.send_json({"error": "Invalid JSON"})
                    continue

                if not isinstance(data, dict):
                    await ws.send_json({"error": "Expected JSON object"})
                    continue

                if data.get("type") == "session/permission_response":
                    client._handle_permission_response(data)
                    continue

                response = await dispatch_message(client, agent, ws, data)
                if response is not None:
                    await ws.send_json(response)
            elif msg.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
                break
    finally:
        client._active.pop(ws, None)
        client.remove_websocket(ws)
        logger.info("WebSocket disconnected")

    return ws


def build_app(client: WebClient, agent: Agent) -> web.Application:
    """Build and return the aiohttp Application."""
    app = web.Application()
    app[AGENT_KEY] = agent
    app[CLIENT_KEY] = client

    async def _add_csp_header(request: web.Request, response: web.StreamResponse) -> None:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self' ws: wss:"
        )

    app.on_response_prepare.append(_add_csp_header)

    # Prefer package-data dir (_static/); fall back to old path for compatibility.
    static_dir = Path(__file__).parent.parent.parent / "_static"
    if not static_dir.exists():
        static_dir = Path(__file__).parent.parent.parent / "static"
    app.router.add_get("/ws", handle_websocket)

    if static_dir.exists():
        index = static_dir / "index.html"

        async def _serve_index(request: web.Request) -> web.StreamResponse:
            return web.FileResponse(index)

        app.router.add_get("/", _serve_index)
        app.router.add_static("/", static_dir, name="static")
    else:
        logger.warning("Static directory not found at %s; web UI not served", static_dir)
    return app


async def run(
    client: WebClient,
    agent: Agent,
    host: str = "127.0.0.1",
    port: int = 8080,
) -> None:
    """Start the aiohttp web server."""
    if client.store.sessions_dir is not None:
        client.store.sessions_dir.mkdir(parents=True, exist_ok=True)

    app = build_app(client, agent)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info("Web server started on http://%s:%d", host, port)

    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await runner.cleanup()
