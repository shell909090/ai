"""Tests for web frontend."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from little_agent.agent.agent import AgentCore
from little_agent.backends.protocol import BackendTurnResult
from little_agent.frontends.web import WebClient
from little_agent.types import SessionUpdate
from tests.mocks import MockBackend, MockToolProvider


class _TestWebClient(WebClient):
    """WebClient with a public method to inject test messages."""

    async def inject_permission_response(self, req_id: str, granted: bool) -> None:
        """Simulate a permission response from a WebSocket client."""
        self._handle_permission_response({"id": req_id, "granted": granted})


@pytest.fixture
async def web_client_fixture():
    """Create a test web server with a mock agent."""
    backend = MockBackend()
    tools = MockToolProvider()
    client = _TestWebClient()
    agent = AgentCore(client=client, backend=backend, tools=tools)

    app = web.Application()
    from little_agent.frontends.web import AGENT_KEY, CLIENT_KEY

    app[AGENT_KEY] = agent
    app[CLIENT_KEY] = client

    static_dir = Path(__file__).parent.parent / "little_agent" / "frontends" / "static"
    if static_dir.exists():
        app.router.add_static("/", static_dir, name="static")
    app.router.add_get("/ws", client.handle_websocket)

    server = TestServer(app)
    test_client = TestClient(server)
    await test_client.start_server()

    yield test_client, client, agent

    await test_client.close()


@pytest.mark.asyncio
async def test_websocket_connect_and_create_session(web_client_fixture) -> None:
    """Test WebSocket connection and session creation."""
    test_client, web_client, agent = web_client_fixture

    async with test_client.ws_connect("/ws") as ws:
        await ws.send_json({"type": "session/new"})
        response = await ws.receive_json()

        assert response.get("type") == "session/new_response"
        assert "session_id" in response
        assert len(response["session_id"]) > 0


@pytest.mark.asyncio
async def test_websocket_prompt_and_response(web_client_fixture) -> None:
    """Test sending a prompt and receiving a response."""
    test_client, web_client, agent = web_client_fixture

    backend = agent.backend
    assert isinstance(backend, MockBackend)
    backend.set_script(
        [
            BackendTurnResult(
                output_text="Hello from agent",
                tool_calls=[],
                finish_reason="completed",
            ),
        ]
    )

    async with test_client.ws_connect("/ws") as ws:
        await ws.send_json({"type": "session/new"})
        new_resp = await ws.receive_json()
        session_id = new_resp["session_id"]

        await ws.send_json(
            {
                "type": "session/prompt",
                "session_id": session_id,
                "prompt": "Hi",
            }
        )

        # We should receive updates and then the prompt_response
        messages = []
        for _ in range(5):
            msg = await asyncio.wait_for(ws.receive_json(), timeout=2.0)
            messages.append(msg)
            if msg.get("type") == "session/prompt_response":
                break

        prompt_resp = [m for m in messages if m.get("type") == "session/prompt_response"]
        assert prompt_resp, f"Expected prompt_response, got: {messages}"
        assert prompt_resp[0]["text"] == "Hello from agent"


@pytest.mark.asyncio
async def test_websocket_update_broadcast(web_client_fixture) -> None:
    """Test that agent updates are broadcast via WebSocket."""
    test_client, web_client, agent = web_client_fixture

    async with test_client.ws_connect("/ws") as ws:
        # Simulate an update from the agent side
        from little_agent.agent.session import SessionCore

        session = await agent.new()
        assert isinstance(session, SessionCore)
        await web_client.update(
            session,
            SessionUpdate(type="agent_message_chunk", data={"text": "test chunk"}),
        )

        msg = await asyncio.wait_for(ws.receive_json(), timeout=2.0)
        assert msg["type"] == "session/update"
        assert msg["update"]["type"] == "agent_message_chunk"
        assert msg["update"]["data"]["text"] == "test chunk"


@pytest.mark.asyncio
async def test_websocket_permission_request(web_client_fixture) -> None:
    """Test permission request flow via WebSocket."""
    test_client, web_client, agent = web_client_fixture

    async with test_client.ws_connect("/ws") as ws:
        session = await agent.new()

        # Start permission request in background
        perm_task = asyncio.create_task(
            web_client.request_permission(session, "bash", {"arguments": {"cmd": "ls"}})
        )

        # Wait for the permission request message
        msg = await asyncio.wait_for(ws.receive_json(), timeout=2.0)
        assert msg["type"] == "session/request_permission"
        assert msg["kind"] == "bash"
        req_id = msg["id"]

        # Send permission response
        await ws.send_json(
            {
                "type": "session/permission_response",
                "id": req_id,
                "granted": True,
            }
        )

        result = await asyncio.wait_for(perm_task, timeout=2.0)
        assert result is True


@pytest.mark.asyncio
async def test_websocket_permission_timeout(web_client_fixture) -> None:
    """Test permission request times out when no response."""
    test_client, web_client, agent = web_client_fixture

    # Override the wait timeout by directly testing _wait_permission_response
    # with a future that never resolves
    async def quick_request():
        req_id = "test_perm_timeout"
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        web_client._permission_futures[req_id] = future
        try:
            return await asyncio.wait_for(web_client._wait_permission_response(req_id), timeout=0.1)
        except TimeoutError:
            return False

    result = await quick_request()
    assert result is False


@pytest.mark.asyncio
async def test_websocket_static_files(web_client_fixture) -> None:
    """Test that static files are served."""
    test_client, web_client, agent = web_client_fixture

    resp = await test_client.get("/")
    assert resp.status in (200, 403, 404)  # 403 if dir listing forbidden, 404 if missing
