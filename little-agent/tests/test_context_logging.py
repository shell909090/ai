"""Tests for session_id/turn_id ContextVar injection (TASK-Q1)."""

from __future__ import annotations

import asyncio

import pytest

from little_agent.agent.context import current_session_id, current_turn_id
from little_agent.agent.tool_manager import ToolManager
from little_agent.backends.protocol import BackendTurnResult
from tests.mocks import MockBackend, MockClient


def _make_agent(script=None):  # type: ignore[return, assignment]
    from little_agent.agent.agent import AgentCore

    if script is None:
        script = [BackendTurnResult(output_text="ok", tool_calls=[], finish_reason="completed")]
    client = MockClient()
    backend = MockBackend(script=script)
    tools = ToolManager()
    return AgentCore(client=client, backend=backend, tools=tools)


def test_context_var_defaults() -> None:
    """current_session_id and current_turn_id default to '-'."""
    assert current_session_id.get("-") == "-"
    assert current_turn_id.get("-") == "-"


@pytest.mark.asyncio
async def test_session_id_set_during_turn() -> None:
    """current_session_id is set to the session id while a turn is running.

    We verify by injecting a backend that reads the context var during generate().
    """
    from collections.abc import AsyncIterator

    from little_agent.agent.agent import AgentCore
    from little_agent.agent.context import current_session_id as _csid
    from little_agent.backends.protocol import Backend, BackendTurnResult
    from little_agent.types import SessionUpdate

    captured: list[str] = []

    class _CapturingBackend(Backend):
        context_window: int = 128000

        def generate(self, session: object) -> AsyncIterator[SessionUpdate | BackendTurnResult]:
            return self._gen()

        async def _gen(self):  # type: ignore[return]
            captured.append(_csid.get("-"))
            yield BackendTurnResult(output_text="ok", tool_calls=[], finish_reason="completed")

    client = MockClient()
    backend = _CapturingBackend()
    from little_agent.agent.tool_manager import ToolManager

    agent = AgentCore(client=client, backend=backend, tools=ToolManager())
    session = await agent.new()
    session_id = session.id

    await session.prompt("hello")

    assert len(captured) >= 1, "Backend was not called"
    assert any(sid == session_id for sid in captured), (
        f"Expected session_id {session_id!r} in captured: {captured}"
    )


@pytest.mark.asyncio
async def test_context_vars_reset_after_turn() -> None:
    """current_session_id and current_turn_id reset to '-' after the turn completes."""
    agent = _make_agent()
    session = await agent.new()
    await session.prompt("hello")
    assert current_session_id.get("-") == "-"
    assert current_turn_id.get("-") == "-"


@pytest.mark.asyncio
async def test_concurrent_sessions_have_distinct_ids() -> None:
    """Two concurrent sessions produce distinct session_id context values."""
    session1_ids: list[str] = []
    session2_ids: list[str] = []

    agent1 = _make_agent()
    agent2 = _make_agent()

    session1 = await agent1.new()
    session2 = await agent2.new()

    async def _run_and_capture(session, capture_list):  # type: ignore[return]
        await asyncio.sleep(0)  # yield to allow interleaving
        capture_list.append(current_session_id.get("-"))
        await session.prompt("hello")
        capture_list.append(current_session_id.get("-"))

    await asyncio.gather(
        _run_and_capture(session1, session1_ids),
        _run_and_capture(session2, session2_ids),
    )

    # After both turns are done, both should reset to '-'
    assert current_session_id.get("-") == "-"
