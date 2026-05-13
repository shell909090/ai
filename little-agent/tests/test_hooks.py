"""Tests for the Hook system."""

from __future__ import annotations

import pytest

from little_agent.agent.agent import AgentCore
from little_agent.agent.tool_manager import ToolManager
from little_agent.backends.protocol import BackendToolCall, BackendTurnResult
from little_agent.tools.protocol import ToolArgDef, ToolDef
from little_agent.types import Hook, Session
from tests.mocks import MockBackend, MockClient, MockToolProvider

# ---------------------------------------------------------------------------
# Recording helpers
# ---------------------------------------------------------------------------


class RecordingHook(Hook):
    """Records every method call by name."""

    def __init__(self, name: str, record: list[str]) -> None:
        self._name = name
        self._record = record

    async def on_turn_start(self, session: Session) -> None:
        self._record.append(f"{self._name}:on_turn_start")

    async def on_turn_end(self, session: Session) -> None:
        self._record.append(f"{self._name}:on_turn_end")

    async def on_tool_call(self, session: Session) -> None:
        self._record.append(f"{self._name}:on_tool_call")

    async def on_tool_result(self, session: Session) -> None:
        self._record.append(f"{self._name}:on_tool_result")

    async def on_compress(self, session: Session) -> None:
        self._record.append(f"{self._name}:on_compress")

    async def on_fork(self, source: Session, forked: Session) -> None:
        self._record.append(f"{self._name}:on_fork")

    async def on_cancel(self, session: Session) -> None:
        self._record.append(f"{self._name}:on_cancel")


def _make_agent(
    backend: MockBackend,
    hooks: list[Hook] | None = None,
    tools: MockToolProvider | None = None,
) -> AgentCore:
    """Create a minimal AgentCore for testing."""
    from little_agent.agent.permissions import YesManChecker

    tool_mgr = ToolManager()
    tool_mgr.register(tools if tools is not None else MockToolProvider())
    return AgentCore(
        client=MockClient(),
        backend=backend,
        tools=tool_mgr,
        permissions=YesManChecker(),
        hooks=hooks or [],
    )


# ---------------------------------------------------------------------------
# (a) Multiple hooks called in order
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multiple_hooks_called_in_order() -> None:
    """Hooks registered first must fire before hooks registered later."""
    record: list[str] = []
    hook_a = RecordingHook("A", record)
    hook_b = RecordingHook("B", record)

    backend = MockBackend(
        [BackendTurnResult(output_text="hi", tool_calls=[], finish_reason="completed")]
    )
    agent = _make_agent(backend, hooks=[hook_a, hook_b])
    session = await agent.new()
    await session.prompt("hello")

    # Both hooks must have fired on_turn_start and on_turn_end in A-before-B order.
    starts = [e for e in record if e.endswith(":on_turn_start")]
    ends = [e for e in record if e.endswith(":on_turn_end")]
    assert starts == ["A:on_turn_start", "B:on_turn_start"]
    assert ends == ["A:on_turn_end", "B:on_turn_end"]


# ---------------------------------------------------------------------------
# (b) Hook with only some methods overridden – others are no-ops
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_partial_hook_no_op_methods() -> None:
    """A hook that only overrides on_turn_end does not raise on other events."""

    class TurnEndOnly(Hook):
        called = False

        async def on_turn_end(self, session: Session) -> None:
            TurnEndOnly.called = True

    hook = TurnEndOnly()
    backend = MockBackend(
        [BackendTurnResult(output_text="ok", tool_calls=[], finish_reason="completed")]
    )
    agent = _make_agent(backend, hooks=[hook])
    session = await agent.new()
    await session.prompt("hello")
    assert TurnEndOnly.called


# ---------------------------------------------------------------------------
# (c) Hook that raises – doesn't block other hooks or main flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_failing_hook_does_not_block_others() -> None:
    """A hook that raises an exception must not prevent other hooks from firing."""

    class BrokenHook(Hook):
        async def on_turn_end(self, session: Session) -> None:
            raise RuntimeError("boom")

    record: list[str] = []
    good_hook = RecordingHook("good", record)
    bad_hook = BrokenHook()

    backend = MockBackend(
        [BackendTurnResult(output_text="fine", tool_calls=[], finish_reason="completed")]
    )
    # bad_hook first so good_hook must still fire after the failure
    agent = _make_agent(backend, hooks=[bad_hook, good_hook])
    session = await agent.new()
    result = await session.prompt("hello")
    assert result == ("end_turn", "fine")
    assert "good:on_turn_end" in record


# ---------------------------------------------------------------------------
# (d) All 7 hook points fire
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_turn_start_fires() -> None:
    """on_turn_start fires before the turn runs."""
    record: list[str] = []
    hook = RecordingHook("h", record)
    backend = MockBackend(
        [BackendTurnResult(output_text="yes", tool_calls=[], finish_reason="completed")]
    )
    agent = _make_agent(backend, hooks=[hook])
    session = await agent.new()
    await session.prompt("go")
    assert "h:on_turn_start" in record


@pytest.mark.asyncio
async def test_on_turn_end_fires() -> None:
    """on_turn_end fires after turn completes."""
    record: list[str] = []
    hook = RecordingHook("h", record)
    backend = MockBackend(
        [BackendTurnResult(output_text="yes", tool_calls=[], finish_reason="completed")]
    )
    agent = _make_agent(backend, hooks=[hook])
    session = await agent.new()
    await session.prompt("go")
    assert "h:on_turn_end" in record


@pytest.mark.asyncio
async def test_on_tool_call_and_result_fire() -> None:
    """on_tool_call and on_tool_result both fire when a tool is invoked."""
    record: list[str] = []
    hook = RecordingHook("h", record)

    tools = MockToolProvider(
        tools={"echo": ToolDef(desc="Echo", args=[ToolArgDef("text", "string", "text", True)])},
        responses={"echo": "echoed"},
    )
    backend = MockBackend(
        [
            BackendTurnResult(
                output_text="",
                tool_calls=[
                    BackendToolCall(call_id="c1", tool_name="echo", arguments={"text": "hi"})
                ],
                finish_reason="tool_call",
            ),
            BackendTurnResult(output_text="done", tool_calls=[], finish_reason="completed"),
        ]
    )
    agent = _make_agent(backend, hooks=[hook], tools=tools)
    session = await agent.new()
    await session.prompt("call echo")
    assert "h:on_tool_call" in record
    assert "h:on_tool_result" in record


@pytest.mark.asyncio
async def test_on_fork_fires() -> None:
    """on_fork fires when session.fork() is called."""
    record: list[str] = []
    hook = RecordingHook("h", record)
    backend = MockBackend(
        [BackendTurnResult(output_text="yes", tool_calls=[], finish_reason="completed")]
    )
    agent = _make_agent(backend, hooks=[hook])
    session = await agent.new()
    await session.prompt("hello")
    await session.fork()
    assert "h:on_fork" in record


@pytest.mark.asyncio
async def test_on_cancel_fires() -> None:
    """on_cancel fires when a turn is cancelled while the backend is streaming."""
    import asyncio
    from collections.abc import AsyncGenerator

    from little_agent.types import SessionUpdate

    record: list[str] = []
    hook = RecordingHook("h", record)

    backend = MockBackend()
    tools = MockToolProvider(
        tools={"echo": ToolDef(desc="echo", args=[])}, responses={"echo": "ok"}
    )

    # Backend sleeps 0.5 s then returns a tool_call; cancel fires during the sleep.
    async def slow_gen(session: object) -> AsyncGenerator[SessionUpdate | BackendTurnResult, None]:
        await asyncio.sleep(0.5)
        yield BackendTurnResult(
            output_text="",
            tool_calls=[BackendToolCall(call_id="c1", tool_name="echo", arguments={})],
            finish_reason="tool_call",
        )

    backend.set_generate_fn(slow_gen)
    agent = _make_agent(backend, hooks=[hook], tools=tools)
    session = await agent.new()

    result_holder: list[tuple[str, str]] = []

    async def run_prompt() -> None:
        result_holder.append(await session.prompt("hi"))

    task = asyncio.create_task(run_prompt())
    await asyncio.sleep(0.1)  # let backend start its sleep
    await session.cancel()
    await task
    assert result_holder[0][0] == "cancelled"
    assert "h:on_cancel" in record


@pytest.mark.asyncio
async def test_on_compress_fires() -> None:
    """on_compress fires when a compressor runs."""
    from little_agent.agent.nodes import Node

    record: list[str] = []
    hook = RecordingHook("h", record)

    class MockCompressor:
        async def compress(self, messages: list[Node]) -> tuple[str, list[Node]]:
            return "compressed summary", messages

    backend = MockBackend(
        [BackendTurnResult(output_text="ok", tool_calls=[], finish_reason="completed")]
    )
    tool_mgr = ToolManager()
    tool_mgr.register(MockToolProvider())
    from little_agent.agent.permissions import YesManChecker

    agent = AgentCore(
        client=MockClient(),
        backend=backend,
        tools=tool_mgr,
        permissions=YesManChecker(),
        hooks=[hook],
        compressor=MockCompressor(),
    )
    session = await agent.new()
    # Trigger compress manually (not turn-based) to avoid race with _schedule_compress
    await session.prompt("go")
    # The post-turn compress may not trigger in tests; call compress directly.
    await session.compress()
    assert "h:on_compress" in record
