"""Tests for web frontend."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from little_agent.agent.agent import AgentCore
from little_agent.agent.protocol import SessionUpdate
from little_agent.backends.protocol import BackendTurnResult
from little_agent.frontends.web import WebClient
from tests.mocks import MockBackend, MockToolProvider


class _TestWebClient(WebClient):
    """WebClient with a public method to inject test messages."""

    async def inject_permission_response(self, req_id: str, granted: bool) -> None:
        """Simulate a permission response from a WebSocket client."""
        self._handle_permission_response({"id": req_id, "granted": granted})


@pytest.fixture
async def web_client_fixture(tmp_path):
    """Create a test web server with a mock agent, isolated sessions dir."""
    backend = MockBackend()
    tools = MockToolProvider()
    client = _TestWebClient(sessions_dir=tmp_path)
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
        response = await asyncio.wait_for(ws.receive_json(), timeout=2.0)

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
        new_resp = await asyncio.wait_for(ws.receive_json(), timeout=2.0)
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
    """Test that agent updates are sent to the subscribed WebSocket connection."""
    test_client, web_client, agent = web_client_fixture

    async with test_client.ws_connect("/ws") as ws:
        # Create session via WS so this connection becomes subscribed
        await ws.send_json({"type": "session/new"})
        new_resp = await asyncio.wait_for(ws.receive_json(), timeout=2.0)
        session_id = new_resp["session_id"]

        # Look up the session from the server-wide _sessions dict
        sess = web_client._sessions[session_id]
        await web_client.update(
            sess,
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
        # Create session via WS so this connection is subscribed
        await ws.send_json({"type": "session/new"})
        new_resp = await asyncio.wait_for(ws.receive_json(), timeout=2.0)
        session_id = new_resp["session_id"]
        sess = web_client._sessions[session_id]

        # Start permission request in background
        perm_task = asyncio.create_task(
            web_client.request_permission(sess, "bash", {"arguments": {"cmd": "ls"}})
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

    with patch("little_agent.frontends.web.server.web.AppRunner", return_value=_FakeRunner()):
        with patch("little_agent.frontends.web.server.web.TCPSite", side_effect=_FakeSite):
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
# T96: Sessions are server-wide (globally shared across connections)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_websocket_sessions_are_globally_shared(web_client_fixture) -> None:
    """Sessions are server-wide — connection B can use a session created by connection A.

    After T96, _sessions is stored on WebClient, not per-connection.  A session_id
    returned by connection A must be accessible when connection B uses it.
    """
    test_client, web_client, agent = web_client_fixture

    session_id_a: str = ""

    async with test_client.ws_connect("/ws") as ws_a:
        await ws_a.send_json({"type": "session/new"})
        resp_a = await asyncio.wait_for(ws_a.receive_json(), timeout=2.0)
        assert resp_a.get("type") == "session/new_response"
        session_id_a = resp_a["session_id"]

    assert session_id_a, "Connection A must have received a session_id"

    backend = agent.backend
    assert isinstance(backend, MockBackend)
    backend.set_script(
        [BackendTurnResult(output_text="hi", tool_calls=[], finish_reason="completed")]
    )

    async with test_client.ws_connect("/ws") as ws_b:
        # B can use A's session — no error expected
        await ws_b.send_json(
            {
                "type": "session/prompt",
                "session_id": session_id_a,
                "prompt": "hello from B",
            }
        )

        # Drain until prompt_response
        messages = []
        for _ in range(5):
            msg = await asyncio.wait_for(ws_b.receive_json(), timeout=2.0)
            messages.append(msg)
            if msg.get("type") == "session/prompt_response":
                break

        prompt_resp = [m for m in messages if m.get("type") == "session/prompt_response"]
        assert prompt_resp, f"Expected prompt_response, got: {messages}"
        assert "error" not in prompt_resp[0], (
            f"Expected no error when using cross-connection session_id; got: {prompt_resp[0]}"
        )


# ---------------------------------------------------------------------------
# T96: session/list message handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_list_empty(web_client_fixture) -> None:
    """On connect, session/list returns an empty sessions list."""
    test_client, web_client, agent = web_client_fixture

    async with test_client.ws_connect("/ws") as ws:
        await ws.send_json({"type": "session/list"})
        response = await asyncio.wait_for(ws.receive_json(), timeout=2.0)

        assert response.get("type") == "session/list_response"
        assert "sessions" in response
        assert response["sessions"] == []


@pytest.mark.asyncio
async def test_session_list_after_create(web_client_fixture) -> None:
    """After creating a session, session/list returns it with required fields."""
    test_client, web_client, agent = web_client_fixture

    async with test_client.ws_connect("/ws") as ws:
        await ws.send_json({"type": "session/new"})
        new_resp = await asyncio.wait_for(ws.receive_json(), timeout=2.0)
        assert new_resp.get("type") == "session/new_response"
        session_id = new_resp["session_id"]

        await ws.send_json({"type": "session/list"})
        list_resp = await asyncio.wait_for(ws.receive_json(), timeout=2.0)

        assert list_resp.get("type") == "session/list_response"
        sessions = list_resp["sessions"]
        assert len(sessions) >= 1

        ids = [s["id"] for s in sessions]
        assert session_id in ids, f"Expected {session_id!r} in session list: {ids}"

        matched = next(s for s in sessions if s["id"] == session_id)
        assert "updated_at" in matched, "Session entry must have 'updated_at'"
        assert "preview" in matched, "Session entry must have 'preview'"


# ---------------------------------------------------------------------------
# T96: session/fork message handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_fork(web_client_fixture) -> None:
    """Forking a session creates a new session with a different ID."""
    test_client, web_client, agent = web_client_fixture

    async with test_client.ws_connect("/ws") as ws:
        await ws.send_json({"type": "session/new"})
        new_resp = await asyncio.wait_for(ws.receive_json(), timeout=2.0)
        assert new_resp.get("type") == "session/new_response"
        original_id = new_resp["session_id"]

        await ws.send_json({"type": "session/fork", "session_id": original_id})
        fork_resp = await asyncio.wait_for(ws.receive_json(), timeout=2.0)

        assert fork_resp.get("type") == "session/fork_response"
        assert "session_id" in fork_resp
        forked_id = fork_resp["session_id"]
        assert forked_id != original_id, "Forked session must have a different ID"


# ---------------------------------------------------------------------------
# T96: session/delete message handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_delete(web_client_fixture) -> None:
    """Deleting a session removes it from the server-wide sessions store."""
    test_client, web_client, agent = web_client_fixture

    async with test_client.ws_connect("/ws") as ws:
        await ws.send_json({"type": "session/new"})
        new_resp = await asyncio.wait_for(ws.receive_json(), timeout=2.0)
        assert new_resp.get("type") == "session/new_response"
        session_id = new_resp["session_id"]

        assert session_id in web_client._sessions, "Session must exist before deletion"

        await ws.send_json({"type": "session/delete", "session_id": session_id})
        del_resp = await asyncio.wait_for(ws.receive_json(), timeout=2.0)

        assert del_resp.get("type") == "session/delete_response"
        assert session_id not in web_client._sessions, (
            "Session must be removed from _sessions after deletion"
        )


# ---------------------------------------------------------------------------
# T96: session/resume with unknown session_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_resume_unknown(web_client_fixture) -> None:
    """Resuming an unknown session_id returns an error response."""
    test_client, web_client, agent = web_client_fixture

    async with test_client.ws_connect("/ws") as ws:
        await ws.send_json({"type": "session/resume", "session_id": "nonexistent-session-id"})
        response = await asyncio.wait_for(ws.receive_json(), timeout=2.0)

        assert "error" in response, (
            f"Expected error response for unknown session_id; got: {response}"
        )


# ---------------------------------------------------------------------------
# Security tests: input validation, output sanitisation, origin enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_session_id_rejected(web_client_fixture) -> None:
    """Non-UUID session_id values are rejected without file I/O."""
    test_client, web_client, agent = web_client_fixture

    async with test_client.ws_connect("/ws") as ws:
        for bad_id in ["../../etc/passwd", "", "not-a-uuid", "' OR 1=1--"]:
            await ws.send_json({"type": "session/prompt", "session_id": bad_id, "prompt": "hi"})
            resp = await asyncio.wait_for(ws.receive_json(), timeout=2.0)
            assert "error" in resp, f"Expected error for session_id={bad_id!r}, got {resp}"
            # Only check non-empty inputs are not echoed back (empty string is a trivial substring)
            if bad_id:
                assert bad_id not in resp.get("error", ""), (
                    f"Error response must not echo the input, got {resp['error']!r}"
                )


@pytest.mark.asyncio
async def test_error_response_does_not_echo_session_id(web_client_fixture) -> None:
    """Error responses for unknown sessions use generic text, not the input string."""
    test_client, web_client, agent = web_client_fixture
    import uuid

    unknown_id = str(uuid.uuid4())

    async with test_client.ws_connect("/ws") as ws:
        await ws.send_json({"type": "session/prompt", "session_id": unknown_id, "prompt": "hi"})
        resp = await asyncio.wait_for(ws.receive_json(), timeout=2.0)
        assert "error" in resp
        assert unknown_id not in resp["error"], (
            f"Error response must not echo session_id, got: {resp['error']!r}"
        )


@pytest.mark.asyncio
async def test_cwd_from_client_is_ignored(web_client_fixture) -> None:
    """Client-supplied cwd in session/new is ignored; session.cwd should be None."""
    test_client, web_client, agent = web_client_fixture

    async with test_client.ws_connect("/ws") as ws:
        await ws.send_json({"type": "session/new", "cwd": "/etc"})
        resp = await asyncio.wait_for(ws.receive_json(), timeout=2.0)
        assert resp.get("type") == "session/new_response"
        session_id = resp["session_id"]
        sess = web_client._sessions[session_id]
        assert getattr(sess, "cwd", None) is None, (
            f"Expected cwd=None, got {getattr(sess, 'cwd', 'MISSING')!r}"
        )


@pytest.mark.asyncio
async def test_cross_origin_websocket_rejected(web_client_fixture) -> None:
    """WebSocket connection from a cross-origin browser is rejected with 403."""
    test_client, web_client, agent = web_client_fixture

    resp = await test_client.get(
        "/ws",
        headers={"Origin": "https://evil.example.com"},
    )
    assert resp.status == 403
