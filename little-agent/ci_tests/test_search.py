"""CI integration tests: compact and search_session."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from little_agent.agent.agent import AgentCore
from little_agent.agent.compressor import LLMCompressor
from little_agent.agent.nodes import ToolResultNode
from little_agent.agent.permissions import YesManChecker
from little_agent.agent.session_store import SessionJSONLStore
from little_agent.tools.bash import BashToolProvider
from little_agent.agent.tool_manager import ToolManager
from tests.mocks import MockClient

from .helpers import make_backend, walk_chain

pytestmark = [pytest.mark.ci, pytest.mark.timeout(120)]


@pytest.mark.asyncio
async def test_compact_search_session(ci_config: dict[str, Any], tmp_path: Path) -> None:
    """After compacting session with keyword in turn 1, search_session still finds it."""
    backend = make_backend(ci_config)
    keyword = "f1-unique-keyword-zq7r9"
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()

    store = SessionJSONLStore(sessions_dir=str(sessions_dir))
    tools = ToolManager()
    tools.register(BashToolProvider())
    tools.register(store)

    compressor = LLMCompressor(backend, keep_turns=1)
    client: MockClient = MockClient()
    agent = AgentCore(
        client=client,
        backend=backend,
        tools=tools,
        compressor=compressor,
        hooks=[store],
        permissions=YesManChecker(),
    )
    session = await agent.new()

    reason1, _ = await session.prompt(
        f"Remember this unique identifier: {keyword}. Just say OK."
    )
    assert reason1 == "end_turn"

    reason2, _ = await session.prompt("Say: two")
    assert reason2 == "end_turn"
    reason3, _ = await session.prompt("Say: three")
    assert reason3 == "end_turn"

    await session.compress()
    assert session.summaries, "session.summaries should be non-empty after compress"

    reason4, _text4 = await session.prompt(
        f"Use the search_session tool to search for '{keyword}'. Report what you find."
    )
    assert reason4 == "end_turn"

    chain4 = walk_chain(session)
    tool_results = [n for n in chain4 if isinstance(n, ToolResultNode)]
    found_keyword = any(keyword in str(r.results) for r in tool_results)
    assert found_keyword, (
        f"search_session result should contain '{keyword}' from compressed JSONL history"
    )
