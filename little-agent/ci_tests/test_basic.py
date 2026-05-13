"""CI integration tests: basic conversation."""

from __future__ import annotations

import asyncio
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


@pytest.mark.asyncio
async def test_multi_turn_conversation(ci_config: dict[str, Any]) -> None:
    """Verify that context is retained across multiple prompt turns."""
    agent, client = build_agent(ci_config)
    session = await agent.new()

    reason1, _ = await session.prompt("Remember the word: zebra. Just say OK.")
    assert reason1 == "end_turn"

    reason2, text2 = await session.prompt("What word did I ask you to remember?")
    assert reason2 == "end_turn"
    assert "zebra" in text2.lower(), f"Agent should recall 'zebra' from context, got: {text2!r}"


@pytest.mark.asyncio
async def test_cancel_in_flight(ci_config: dict[str, Any]) -> None:
    """Cancel a prompt while a bash tool is running; verify stop_reason is 'cancelled'.

    Uses a long-running bash tool (sleep 30) so that cancel reliably fires during
    tool execution rather than racing against backend streaming completion.
    """
    agent, client = build_agent(ci_config)
    session = await agent.new()

    async def _cancel_after_delay() -> None:
        await asyncio.sleep(5)
        await session.cancel()

    prompt_task = asyncio.create_task(
        session.prompt("Run the bash command `sleep 30` and wait for it to finish.")
    )
    cancel_task = asyncio.create_task(_cancel_after_delay())

    reason, _ = await prompt_task
    await cancel_task

    assert reason == "cancelled", f"Expected 'cancelled' stop reason, got {reason!r}"
