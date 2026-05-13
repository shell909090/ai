"""CI integration tests: web frontend commands."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from little_agent.agent.agent import AgentCore
from little_agent.agent.compressor import LLMCompressor
from little_agent.agent.permissions import YesManChecker
from little_agent.frontends.web.client import WebClient
from little_agent.frontends.web.handlers import (
    do_session_compact,
    do_session_new,
    do_session_prompt,
)
from little_agent.tools.bash import BashToolProvider
from little_agent.agent.tool_manager import ToolManager

from .helpers import make_backend, make_ws_mock

pytestmark = [pytest.mark.ci, pytest.mark.timeout(120)]


@pytest.mark.asyncio
async def test_web_session_prompt(ci_config: dict[str, Any], tmp_path: Path) -> None:
    """session/new then session/prompt via handler functions; verify prompt_response."""
    backend = make_backend(ci_config)
    tools = ToolManager()
    tools.register(BashToolProvider())
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    web_client = WebClient(sessions_dir=sessions_dir)
    agent = AgentCore(
        client=web_client, backend=backend, tools=tools, permissions=YesManChecker()
    )

    ws = make_ws_mock()
    web_client.add_websocket(ws)

    new_resp = await do_session_new(web_client, agent, ws, {"type": "session/new"})
    assert new_resp is not None
    assert new_resp.get("type") == "session/new_response"
    session_id = new_resp.get("session_id")
    assert isinstance(session_id, str) and session_id

    prompt_resp = await do_session_prompt(
        web_client,
        agent,
        ws,
        {"type": "session/prompt", "session_id": session_id, "prompt": "Say: hello"},
    )
    assert prompt_resp is not None
    assert prompt_resp.get("type") == "session/prompt_response"
    assert prompt_resp.get("stop_reason") == "end_turn"


@pytest.mark.asyncio
async def test_web_compact(ci_config: dict[str, Any], tmp_path: Path) -> None:
    """Do 3 turns via web handlers then session/compact; verify ok=True and summaries set."""
    backend = make_backend(ci_config)
    tools = ToolManager()
    tools.register(BashToolProvider())
    compressor = LLMCompressor(backend, keep_turns=1)
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    web_client = WebClient(sessions_dir=sessions_dir)
    agent = AgentCore(
        client=web_client,
        backend=backend,
        tools=tools,
        compressor=compressor,
        permissions=YesManChecker(),
    )

    ws = make_ws_mock()
    web_client.add_websocket(ws)

    new_resp = await do_session_new(web_client, agent, ws, {"type": "session/new"})
    assert new_resp is not None
    session_id = str(new_resp["session_id"])

    for text in ("Say: one", "Say: two", "Say: three"):
        await do_session_prompt(
            web_client, agent, ws,
            {"type": "session/prompt", "session_id": session_id, "prompt": text},
        )

    compact_resp = await do_session_compact(
        web_client, agent, ws,
        {"type": "session/compact", "session_id": session_id},
    )
    assert compact_resp is not None
    assert compact_resp.get("type") == "session/compact_response"
    assert compact_resp.get("ok") is True, f"compact failed: {compact_resp.get('error')}"

    sess = web_client.store.get_session(session_id)
    assert sess is not None
    assert sess.summaries, "After web compact, session.summaries must be non-empty"
