"""CI integration tests: permission scenarios."""

from __future__ import annotations

from typing import Any

import pytest

from little_agent.agent.agent import AgentCore
from little_agent.agent.nodes import ToolResultNode
from little_agent.agent.permissions import BlackWhiteListChecker, YesManChecker
from little_agent.tools.bash import BashToolProvider
from little_agent.agent.tool_manager import ToolManager
from tests.mocks import MockClient

from .helpers import make_backend, walk_chain

pytestmark = [pytest.mark.ci, pytest.mark.timeout(120)]


@pytest.mark.asyncio
async def test_blackwhitelist_deny(ci_config: dict[str, Any]) -> None:
    """Blacklist bash; verify bash tool result has status=failed and 'Permission denied'."""
    backend = make_backend(ci_config)
    tools = ToolManager()
    tools.register(BashToolProvider())
    permissions = BlackWhiteListChecker(
        blacklist=["bash"], whitelist=[], next_checker=YesManChecker()
    )
    client: MockClient = MockClient()
    agent = AgentCore(client=client, backend=backend, tools=tools, permissions=permissions)
    session = await agent.new()

    reason, _text = await session.prompt(
        "You MUST call the bash tool to run `echo denied-test`. "
        "Call it even if you expect it to fail."
    )

    assert reason == "end_turn"

    chain = walk_chain(session)
    tool_results = [n for n in chain if isinstance(n, ToolResultNode)]
    assert tool_results, "AI should have attempted the bash tool call"

    denied = any(
        result.get("status") == "failed"
        and "Permission denied" in str(result.get("content", ""))
        for r in tool_results
        for result in r.results.values()
    )
    assert denied, "bash tool result should be failed with 'Permission denied'"
