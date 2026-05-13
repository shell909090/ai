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
    """Cancel a prompt while it is running; verify stop_reason is 'cancelled'."""
    agent, client = build_agent(ci_config)
    session = await agent.new()

    async def _cancel_after_delay() -> None:
        await asyncio.sleep(0.05)
        await session.cancel()

    prompt_task = asyncio.create_task(
        session.prompt(
            "Count very slowly from 1 to 100, writing each number on a new line. Do not rush."
        )
    )
    cancel_task = asyncio.create_task(_cancel_after_delay())

    reason, partial_text = await prompt_task
    await cancel_task

    assert reason == "cancelled", (
        f"Expected 'cancelled' stop reason, got {reason!r}. "
        "If the model replied instantly before cancel fired, re-run."
    )
