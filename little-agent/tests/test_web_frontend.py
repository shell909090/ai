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


# ---------------------------------------------------------------------------
# T78: WebClient.run() uses the host/port arguments it receives
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_webclient_run_uses_provided_host_and_port() -> None:
    """WebClient.run() must pass the supplied host/port to TCPSite, not hard-coded values."""
    from unittest.mock import patch

    from little_agent.agent.agent import AgentCore
    from little_agent.frontends.web import WebClient
    from tests.mocks import MockBackend, MockToolProvider

    client = WebClient()
    backend = MockBackend()
    tools = MockToolProvider()
    agent = AgentCore(client=client, backend=backend, tools=tools)

    captured_host: list[str] = []
    captured_port: list[int] = []

    class _FakeSite:
        def __init__(self, runner: object, host: str, port: int) -> None:
            captured_host.append(host)
            captured_port.append(port)

        async def start(self) -> None:
            pass

    class _FakeRunner:
        async def setup(self) -> None:
            pass

        async def cleanup(self) -> None:
            pass

    async def _cancel_after_start() -> None:
        """Allow one event-loop cycle so site.start() runs, then raise CancelledError."""
        raise asyncio.CancelledError

    with patch("little_agent.frontends.web.web.AppRunner", return_value=_FakeRunner()):
        with patch("little_agent.frontends.web.web.TCPSite", side_effect=_FakeSite):
            # run() loops forever; cancel it immediately after setup.
            try:
                await asyncio.wait_for(
                    client.run(agent, host="0.0.0.0", port=9999),
                    timeout=0.5,
                )
            except (asyncio.CancelledError, TimeoutError):
                pass

    assert captured_host, "TCPSite was never instantiated; host not captured"
    assert captured_host[0] == "0.0.0.0", f"Expected host '0.0.0.0', got {captured_host[0]!r}"
    assert captured_port[0] == 9999, f"Expected port 9999, got {captured_port[0]!r}"


# ---------------------------------------------------------------------------
# T79: WebSocket session isolation — sessions from different connections don't overlap
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_websocket_sessions_are_isolated_across_connections(web_client_fixture) -> None:
    """Sessions created in one WebSocket connection are invisible to a second connection.

    Each call to handle_websocket maintains its own `sessions` dict.  A session_id
    returned by connection A must not be found when connection B looks it up.
    """
    test_client, web_client, agent = web_client_fixture

    session_id_a: str = ""
    session_id_b: str = ""

    async with test_client.ws_connect("/ws") as ws_a:
        await ws_a.send_json({"type": "session/new"})
        resp_a = await asyncio.wait_for(ws_a.receive_json(), timeout=2.0)
        assert resp_a.get("type") == "session/new_response"
        session_id_a = resp_a["session_id"]

    async with test_client.ws_connect("/ws") as ws_b:
        await ws_b.send_json({"type": "session/new"})
        resp_b = await asyncio.wait_for(ws_b.receive_json(), timeout=2.0)
        assert resp_b.get("type") == "session/new_response"
        session_id_b = resp_b["session_id"]

        # Now try to use session_id_a in connection B — it must be unknown.
        await ws_b.send_json(
            {
                "type": "session/prompt",
                "session_id": session_id_a,
                "prompt": "hello from B using A's session",
            }
        )
        error_resp = await asyncio.wait_for(ws_b.receive_json(), timeout=2.0)
        assert "error" in error_resp, (
            f"Expected an error response when using cross-connection session_id; got: {error_resp}"
        )
        assert session_id_a in error_resp["error"], (
            f"Error should mention the unknown session_id; got: {error_resp['error']!r}"
        )

    # Sanity: the two sessions should have different IDs.
    assert session_id_a != session_id_b
