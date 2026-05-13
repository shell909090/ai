"""CI integration tests: Hook lifecycle callbacks."""

from __future__ import annotations

from typing import Any

import pytest

from little_agent.agent.agent import AgentCore
from little_agent.types import Hook
from little_agent.agent.permissions import YesManChecker
from little_agent.types import Session
from little_agent.tools.bash import BashToolProvider
from little_agent.agent.tool_manager import ToolManager
from tests.mocks import MockClient

from .helpers import make_backend

pytestmark = [pytest.mark.ci, pytest.mark.timeout(120)]


class _RecordingHook(Hook):
    """Hook that records which lifecycle events fired."""

    def __init__(self) -> None:
        self.events: list[str] = []

    async def on_turn_start(self, session: Session) -> None:
        self.events.append("on_turn_start")

    async def on_turn_end(self, session: Session) -> None:
        self.events.append("on_turn_end")

    async def on_tool_call(self, session: Session) -> None:
        self.events.append("on_tool_call")

    async def on_tool_result(self, session: Session) -> None:
        self.events.append("on_tool_result")


@pytest.mark.asyncio
async def test_hooks_fired_on_tool_turn(ci_config: dict[str, Any]) -> None:
    """Verify on_turn_start/end and on_tool_call/result all fire during a tool turn."""
    backend = make_backend(ci_config)
    tools = ToolManager()
    tools.register(BashToolProvider())
    hook = _RecordingHook()
    client: MockClient = MockClient()
    agent = AgentCore(
        client=client,
        backend=backend,
        tools=tools,
        permissions=YesManChecker(),
        hooks=[hook],
    )
    session = await agent.new()

    reason, _ = await session.prompt(
        "Use the bash tool to run `echo hook-test` and report the output."
    )
    assert reason == "end_turn"

    assert "on_turn_start" in hook.events, "on_turn_start should have fired"
    assert "on_turn_end" in hook.events, "on_turn_end should have fired"
    assert "on_tool_call" in hook.events, "on_tool_call should have fired"
    assert "on_tool_result" in hook.events, "on_tool_result should have fired"


@pytest.mark.asyncio
async def test_hooks_fired_on_fork(ci_config: dict[str, Any]) -> None:
    """Verify on_fork fires when a session is forked."""
    backend = make_backend(ci_config)
    tools = ToolManager()
    tools.register(BashToolProvider())

    class _ForkHook(Hook):
        def __init__(self) -> None:
            self.forked: list[tuple[str, str]] = []

        async def on_fork(self, source: Session, forked: Session) -> None:
            self.forked.append((source.id, forked.id))

    hook = _ForkHook()
    client: MockClient = MockClient()
    agent = AgentCore(
        client=client,
        backend=backend,
        tools=tools,
        permissions=YesManChecker(),
        hooks=[hook],
    )
    session = await agent.new()

    reason, _ = await session.prompt("Say: hello")
    assert reason == "end_turn"

    forked = await session.fork()

    assert len(hook.forked) == 1, "on_fork should have fired exactly once"
    source_id, fork_id = hook.forked[0]
    assert source_id == session.id
    assert fork_id == forked.id
