"""CI integration tests: compressor scenario."""

from __future__ import annotations

from typing import Any

import pytest

from little_agent.agent.agent import AgentCore
from little_agent.agent.compressor import LLMCompressor
from little_agent.agent.permissions import YesManChecker
from little_agent.tools.bash import BashProvider
from little_agent.agent.tool_manager import ToolManager
from tests.mocks import MockClient

from .helpers import make_backend

pytestmark = [pytest.mark.ci, pytest.mark.timeout(120)]


@pytest.mark.asyncio
async def test_auto_compression(ci_config: dict[str, Any]) -> None:
    """With compress_ratio=1e-6, verify summaries are non-empty after 2 turns."""
    backend = make_backend(ci_config)
    tools = ToolManager()
    tools.register(BashProvider())
    compressor = LLMCompressor(backend, keep_turns=1)
    client: MockClient = MockClient()
    agent = AgentCore(
        client=client,
        backend=backend,
        tools=tools,
        compressor=compressor,
        permissions=YesManChecker(),
        # 1e-6 << any realistic token/char ratio, so every turn triggers auto-compress.
        compress_threshold=1e-6,
    )
    session: Any = await agent.new()

    reason1, _ = await session.prompt("Say: one")
    assert reason1 == "end_turn"
    await session.wait_compress()

    reason2, _ = await session.prompt("Say: two")
    assert reason2 == "end_turn"
    await session.wait_compress()

    assert session.summaries, (
        "With compress_ratio=1e-6 and 2 turns, session.summaries should be non-empty after auto-compress"
    )
