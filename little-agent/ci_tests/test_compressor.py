"""CI integration tests: compressor scenario."""

from __future__ import annotations

from typing import Any

import pytest

from little_agent.agent.agent import AgentCore
from little_agent.agent.compressor import LLMCompressor
from little_agent.agent.nodes import SummaryNode
from little_agent.agent.permissions import YesManChecker
from little_agent.tools.bash import BashToolProvider
from little_agent.tools.manager import ToolManager
from tests.mocks import MockClient

from .helpers import make_backend, walk_chain

pytestmark = [pytest.mark.ci, pytest.mark.timeout(120)]


@pytest.mark.asyncio
async def test_auto_compression(ci_config: dict[str, Any]) -> None:
    """With compress_ratio=1e-6, verify SummaryNode appears after 2 turns."""
    backend = make_backend(ci_config)
    tools = ToolManager()
    tools.register(BashToolProvider())
    compressor = LLMCompressor(backend, keep_turns=1, compressed_window_tokens=0)
    client: MockClient = MockClient()
    agent = AgentCore(
        client=client,
        backend=backend,
        tools=tools,
        compressor=compressor,
        permissions=YesManChecker(),
        # 1e-6 << any realistic token/char ratio, so every turn triggers auto-compress.
        compress_ratio=1e-6,
    )
    session: Any = await agent.new()

    reason1, _ = await session.prompt("Say: one")
    assert reason1 == "end_turn"
    await session.wait_compress()

    reason2, _ = await session.prompt("Say: two")
    assert reason2 == "end_turn"
    await session.wait_compress()

    chain = walk_chain(session)
    assert any(isinstance(n, SummaryNode) for n in chain), (
        "With compress_ratio=1e-6 and 2 turns, a SummaryNode should appear after auto-compress"
    )
