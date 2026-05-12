"""CI integration tests: basic conversation."""

from __future__ import annotations

from typing import Any

import pytest

from .helpers import build_agent

pytestmark = [pytest.mark.ci, pytest.mark.timeout(120)]


@pytest.mark.asyncio
async def test_basic_conversation(ci_config: dict[str, Any]) -> None:
    """Send a simple prompt and verify a successful end_turn response."""
    agent, client = build_agent(ci_config)
    session = await agent.new()

    reason, text = await session.prompt("Reply with exactly the word: hello")

    assert reason == "end_turn", f"Unexpected stop reason: {reason}"
    assert text.strip(), "Response should not be empty"
    assert len(client.updates) > 0, "Should have received at least one update"
