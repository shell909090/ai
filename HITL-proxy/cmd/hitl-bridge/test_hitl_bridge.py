"""Tests for hitl-bridge ping functionality."""

import asyncio
import socket
import threading

import pytest
import uvicorn
from mcp.server.fastmcp import FastMCP

import hitl_bridge


def _free_port() -> int:
    """Find a free TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(autouse=True)
def _no_proxy(monkeypatch: pytest.MonkeyPatch):
    """Ensure httpx connects directly to localhost, bypassing any proxy."""
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")


@pytest.fixture()
def sse_url():
    """Start a minimal MCP SSE server and yield its URL."""
    port = _free_port()
    server = FastMCP(name="test-server", host="127.0.0.1", port=port)

    @server.tool()
    def echo(msg: str) -> str:
        """Echo a message back."""
        return msg

    app = server.sse_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    uv_server = uvicorn.Server(config)

    t = threading.Thread(target=uv_server.run, daemon=True)
    t.start()

    # Wait for server to be ready
    while not uv_server.started:
        pass

    yield f"http://127.0.0.1:{port}/sse"

    uv_server.should_exit = True
    t.join(timeout=3)


def test_ping_success(sse_url: str) -> None:
    """Ping against a local MCP SSE server should succeed."""
    asyncio.run(hitl_bridge.ping(sse_url, api_key=""))
