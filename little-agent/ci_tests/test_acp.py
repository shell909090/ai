"""CI integration tests: ACP frontend."""

from __future__ import annotations

from typing import Any

import pytest

from little_agent.agent.agent import AgentCore
from little_agent.agent.permissions import YesManChecker
from little_agent.frontends.acp import AcpClient
from little_agent.tools.bash import BashToolProvider
from little_agent.agent.tool_manager import ToolManager

from .helpers import make_backend

pytestmark = [pytest.mark.ci, pytest.mark.timeout(120)]


@pytest.mark.asyncio
async def test_acp_session_prompt(ci_config: dict[str, Any]) -> None:
    """Call ACP dispatch for session/new + session/prompt; verify stop_reason and text."""
    backend = make_backend(ci_config)
    tools = ToolManager()
    tools.register(BashToolProvider())
    acp_client = AcpClient()
    agent = AgentCore(
        client=acp_client, backend=backend, tools=tools, permissions=YesManChecker()
    )

    new_result = await acp_client._dispatch(agent, "session/new", {})
    assert isinstance(new_result, dict)
    session_id = new_result.get("session_id")
    assert isinstance(session_id, str) and session_id

    prompt_result = await acp_client._dispatch(
        agent,
        "session/prompt",
        {"session_id": session_id, "prompt": "Say: hello"},
    )
    assert isinstance(prompt_result, dict)
    assert prompt_result.get("stop_reason") == "end_turn"
    assert str(prompt_result.get("text", "")).strip(), "Response text should not be empty"


@pytest.mark.asyncio
async def test_acp_save_load(ci_config: dict[str, Any]) -> None:
    """Run a turn, save the session, load it back, verify last message id is preserved."""
    backend = make_backend(ci_config)
    tools = ToolManager()
    tools.register(BashToolProvider())
    acp_client = AcpClient()
    agent = AgentCore(
        client=acp_client, backend=backend, tools=tools, permissions=YesManChecker()
    )

    new_result = await acp_client._dispatch(agent, "session/new", {})
    session_id = str(new_result["session_id"])

    await acp_client._dispatch(
        agent, "session/prompt", {"session_id": session_id, "prompt": "Say: hello"}
    )

    save_result = await acp_client._dispatch(agent, "session/save", {"session_id": session_id})
    assert isinstance(save_result, dict), "session/save should return a dict"

    original_session = acp_client._sessions[session_id]
    original_tail_id = original_session.messages[-1].id if original_session.messages else None

    load_result = await acp_client._dispatch(agent, "session/load", {"data": save_result})
    assert isinstance(load_result, dict)
    loaded_id = load_result.get("session_id")
    assert isinstance(loaded_id, str) and loaded_id

    loaded_session = acp_client._sessions[loaded_id]
    loaded_tail_id = loaded_session.messages[-1].id if loaded_session.messages else None
    assert loaded_tail_id == original_tail_id, "Loaded session last message should match original"
