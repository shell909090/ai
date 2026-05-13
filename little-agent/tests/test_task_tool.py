"""Tests for task tool provider."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from little_agent.agent.agent import AgentCore
from little_agent.agent.nodes import AssistantNode, UserPromptNode
from little_agent.agent.session import SessionCore
from little_agent.agent.tool_manager import ToolManager
from little_agent.backends.protocol import BackendTurnResult
from little_agent.tools.protocol import ToolArgDef, ToolDef
from little_agent.tools.task import TASK_TIMEOUT, TaskToolProvider
from tests.mocks import MockBackend, MockClient, MockToolProvider


@pytest.fixture
def simple_agent() -> AgentCore:
    """AgentCore backed by a single-shot MockBackend."""
    client = MockClient()
    backend = MockBackend(
        script=[BackendTurnResult(output_text="done", tool_calls=[], finish_reason="completed")]
    )
    tools = ToolManager()
    tools.register(
        MockToolProvider(
            tools={
                "echo": ToolDef(
                    desc="Echo the input", args=[ToolArgDef("text", "string", "text", True)]
                )
            }
        )
    )
    return AgentCore(client=client, backend=backend, tools=tools)


def test_task_tool_list() -> None:
    """TaskToolProvider exposes task via __iter__."""
    from unittest.mock import MagicMock

    agent = MagicMock()
    agent.tools.desc_tool.return_value = {}
    provider = TaskToolProvider(agent)
    names = {name for name, _, _ in provider}
    assert "task" in names


@pytest.mark.asyncio
async def test_task_basic(simple_agent: AgentCore) -> None:
    """Task tool returns a completed result for a simple prompt."""
    provider = TaskToolProvider(simple_agent)
    result = await provider._task_dispatch({"prompt": "hello"})
    assert isinstance(result, dict)
    assert result["status"] == "completed"
    assert "output" in result


@pytest.mark.asyncio
async def test_task_missing_prompt() -> None:
    """Task tool returns failed when prompt is absent or not a string."""
    from unittest.mock import MagicMock

    agent = MagicMock()
    agent.tools.desc_tool.return_value = {}
    provider = TaskToolProvider(agent)
    result = await provider._task_dispatch({})
    assert isinstance(result, dict)
    assert result["status"] == "failed"


@pytest.mark.asyncio
async def test_task_timeout(simple_agent: AgentCore) -> None:
    """Task tool returns timeout when asyncio.wait_for raises TimeoutError."""
    provider = TaskToolProvider(simple_agent)

    def _raise_timeout(coro: object, **_: object) -> None:
        if asyncio.iscoroutine(coro):
            coro.close()
        raise TimeoutError

    with patch("little_agent.tools.task.asyncio.wait_for", side_effect=_raise_timeout):
        result = await provider._task_dispatch({"prompt": "test"})

    assert isinstance(result, dict)
    assert result["status"] == "timeout"
    assert str(TASK_TIMEOUT) in str(result.get("output", ""))


@pytest.mark.asyncio
async def test_task_exception(simple_agent: AgentCore) -> None:
    """Task tool returns failed when sub-session raises an unexpected error."""
    provider = TaskToolProvider(simple_agent)

    def _raise_runtime(coro: object, **_: object) -> None:
        if asyncio.iscoroutine(coro):
            coro.close()
        raise RuntimeError("boom")

    with patch("little_agent.tools.task.asyncio.wait_for", side_effect=_raise_runtime):
        result = await provider._task_dispatch({"prompt": "test"})

    assert isinstance(result, dict)
    assert result["status"] == "failed"
    assert "boom" in str(result.get("output", ""))


def test_get_allowed_tools_excludes_task(simple_agent: AgentCore) -> None:
    """Sub-task allowed tools never include task (prevents recursion)."""
    mgr = ToolManager()
    mgr.register(
        MockToolProvider(
            tools={"echo": ToolDef(desc="Echo", args=[ToolArgDef("text", "string", "t", True)])}
        )
    )
    provider = TaskToolProvider(simple_agent)
    mgr.register(provider)
    simple_agent.tools = mgr

    allowed = provider._get_allowed_tools(None)
    assert "task" not in allowed
    assert "echo" in allowed


def test_get_allowed_tools_filter_by_names(simple_agent: AgentCore) -> None:
    """Sub-task allowed tools are limited to requested names, excluding task."""
    mgr = ToolManager()
    mgr.register(
        MockToolProvider(
            tools={
                "echo": ToolDef(desc="Echo", args=[ToolArgDef("text", "string", "t", True)]),
                "add": ToolDef(
                    desc="Add",
                    args=[
                        ToolArgDef("a", "number", "a", True),
                        ToolArgDef("b", "number", "b", True),
                    ],
                ),
            }
        )
    )
    provider = TaskToolProvider(simple_agent)
    simple_agent.tools = mgr

    allowed = provider._get_allowed_tools(["echo"])
    assert "echo" in allowed
    assert "add" not in allowed
    assert "task" not in allowed


@pytest.mark.asyncio
async def test_fork_for_inheritance_tail_none(simple_agent: AgentCore) -> None:
    """_fork_for_inheritance with empty messages returns session with no messages."""
    provider = TaskToolProvider(simple_agent)
    session = SessionCore(session_id="s1", cwd="/tmp", agent=simple_agent)
    session.messages = []

    sub = await provider._fork_for_inheritance(session)

    assert sub.messages == []
    assert sub.id != session.id
    assert sub.cwd == session.cwd
    assert sub.agent is session.agent


@pytest.mark.asyncio
async def test_fork_for_inheritance_tail_no_frozen(simple_agent: AgentCore) -> None:
    """_fork_for_inheritance with node lacking frozen uses it as fork point."""
    provider = TaskToolProvider(simple_agent)
    session = SessionCore(session_id="s1", cwd="/tmp", agent=simple_agent)
    node = UserPromptNode(id="n1", prompt="hi")
    session.messages = [node]

    sub = await provider._fork_for_inheritance(session)

    assert sub.messages == [node]


@pytest.mark.asyncio
async def test_fork_for_inheritance_skips_frozen_nodes(simple_agent: AgentCore) -> None:
    """_fork_for_inheritance skips nodes that have a frozen attribute."""
    provider = TaskToolProvider(simple_agent)
    session = SessionCore(session_id="s1", cwd="/tmp", agent=simple_agent)

    # messages: [head(no frozen), mid(frozen=True), tail(frozen=True)]
    head = UserPromptNode(id="head", prompt="hi")
    mid = AssistantNode(id="mid", text="mid", frozen=True)
    tail = AssistantNode(id="tail", text="tail", frozen=True)
    session.messages = [head, mid, tail]

    sub = await provider._fork_for_inheritance(session)

    assert sub.messages == [head]


@pytest.mark.asyncio
async def test_fork_for_inheritance_partial_frozen(simple_agent: AgentCore) -> None:
    """_fork_for_inheritance stops at first node without frozen attribute."""
    provider = TaskToolProvider(simple_agent)
    session = SessionCore(session_id="s1", cwd="/tmp", agent=simple_agent)

    # messages: [older(frozen=True), prev(no frozen), tail(frozen=True)]
    older = AssistantNode(id="older", text="older", frozen=True)
    prev = UserPromptNode(id="prev", prompt="hi")
    tail = AssistantNode(id="tail", text="tail", frozen=True)
    session.messages = [older, prev, tail]

    sub = await provider._fork_for_inheritance(session)

    assert sub.messages == [older, prev]


@pytest.mark.asyncio
async def test_fork_for_inheritance_all_frozen(simple_agent: AgentCore) -> None:
    """_fork_for_inheritance returns empty messages when all nodes have frozen."""
    provider = TaskToolProvider(simple_agent)
    session = SessionCore(session_id="s1", cwd="/tmp", agent=simple_agent)

    n1 = AssistantNode(id="n1", text="n1", frozen=True)
    n2 = AssistantNode(id="n2", text="n2", frozen=True)
    session.messages = [n1, n2]

    sub = await provider._fork_for_inheritance(session)

    assert sub.messages == []


# ---------------------------------------------------------------------------
# T66: _fork_for_inheritance stops at frozen=False AssistantNode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fork_for_inheritance_stops_at_frozen_false(simple_agent: AgentCore) -> None:
    """_fork_for_inheritance stops traversal at the first frozen=False node.

    The loop walks backwards while frozen is True; a frozen=False node causes
    the loop to stop immediately, and the fork-messages include that very node
    (not just its predecessor).
    """
    provider = TaskToolProvider(simple_agent)
    session = SessionCore(session_id="s1", cwd="/tmp", agent=simple_agent)

    # messages: [head(frozen=True), middle(frozen=False), tail(frozen=True)]
    # Walk from tail: frozen=True → continue; middle: frozen=False → stop.
    # Expected fork-messages include up to and including 'middle'.
    head = AssistantNode(id="head", text="head", frozen=True)
    middle = AssistantNode(id="middle", text="middle", frozen=False)
    tail = AssistantNode(id="tail", text="tail", frozen=True)
    session.messages = [head, middle, tail]

    sub = await provider._fork_for_inheritance(session)

    # The walker stops at 'middle' (frozen=False) so fork includes [head, middle].
    assert sub.messages == [head, middle]


# ---------------------------------------------------------------------------
# T68: CancelledError does not escape _run_scheduler; result_future is set
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scheduler_cancelled_sets_result_future(simple_agent: AgentCore) -> None:
    """When the scheduler task is cancelled, pending result_futures are still resolved.

    The `_run_scheduler` BaseException handler must set all unresolved futures
    before re-raising, so callers of `create_task` / `result_future` never hang.
    """
    provider = TaskToolProvider(simple_agent)

    # Capture the future before the scheduler consumes it.
    captured_future: asyncio.Future[object] | None = None

    async def _patched_execute(spec: object) -> None:  # type: ignore[override]
        # Simulate a long-running sub-task so the scheduler can be cancelled.
        await asyncio.sleep(10)

    provider._execute = _patched_execute  # type: ignore[method-assign]

    # Inject a task spec directly so we can grab its future.
    from little_agent.tools.task import _TaskSpec

    loop = asyncio.get_running_loop()
    future: asyncio.Future[object] = loop.create_future()
    spec = _TaskSpec(task_id=None, depends=[], kwargs={"prompt": "hi"}, result_future=future)
    provider._pending.append(spec)
    captured_future = future

    # Start the scheduler manually.
    scheduler_task = asyncio.create_task(provider._run_scheduler())

    # Give the scheduler a tick to start executing the sub-task.
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    # Cancel the scheduler task.
    scheduler_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass

    # The future must be resolved (not pending) so awaiting it doesn't hang.
    assert captured_future is not None
    assert captured_future.done(), "result_future must be resolved after scheduler cancellation"
    result = captured_future.result()
    assert isinstance(result, dict)
    assert result.get("status") in ("failed", "cancelled")
