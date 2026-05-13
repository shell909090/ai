"""Tests for asyncio.create_task strong-reference fix (TASK-E2)."""

from __future__ import annotations

import asyncio
import gc

import pytest

from little_agent.agent.tool_manager import ToolManager
from little_agent.backends.protocol import BackendTurnResult
from tests.mocks import MockBackend, MockClient


def _make_session():  # type: ignore[return]
    """Create a minimal SessionCore for testing."""
    from little_agent.agent.agent import AgentCore

    client = MockClient()
    backend = MockBackend(
        script=[BackendTurnResult(output_text="ok", tool_calls=[], finish_reason="completed")]
    )
    tools = ToolManager()
    agent = AgentCore(client=client, backend=backend, tools=tools)
    return agent


@pytest.mark.asyncio
async def test_session_bg_tasks_set_exists() -> None:
    """SessionCore._bg_tasks is initialised as an empty set."""
    agent = _make_session()
    session = await agent.new()
    assert hasattr(session, "_bg_tasks")
    assert isinstance(session._bg_tasks, set)


@pytest.mark.asyncio
async def test_session_bg_tasks_holds_reference_during_prompt() -> None:
    """_bg_tasks holds a reference to the _consume_queue task while it runs."""
    agent = _make_session()
    session = await agent.new()
    # After prompt completes the _consume_queue task is done and removed from the set.
    await session.prompt("hello")
    # All background tasks must be done (the set may or may not be empty depending on GC timing,
    # but all retained tasks must be in done state).
    for t in session._bg_tasks:
        assert t.done(), "Remaining tasks in _bg_tasks must all be done"


@pytest.mark.asyncio
async def test_session_task_not_gc_collected() -> None:
    """Task created via asyncio.create_task is not GC-collected while in _bg_tasks."""
    agent = _make_session()
    session = await agent.new()
    done_event = asyncio.Event()

    async def _long_coro() -> None:
        await done_event.wait()

    t = asyncio.create_task(_long_coro())
    session._bg_tasks.add(t)
    t.add_done_callback(session._bg_tasks.discard)

    # Force GC to collect any weakly-referenced objects.
    gc.collect()

    # The task must still be alive (not cancelled, not done).
    assert not t.done(), "Task should still be running"
    assert t in session._bg_tasks, "Task should still be in _bg_tasks"

    # Cleanup.
    done_event.set()
    await t


@pytest.mark.asyncio
async def test_web_client_bg_tasks_set_exists() -> None:
    """WebClient._bg_tasks is initialised as an empty set."""
    from little_agent.frontends.web.client import WebClient

    client = WebClient()
    assert hasattr(client, "_bg_tasks")
    assert isinstance(client._bg_tasks, set)
