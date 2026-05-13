"""Tests for task tool provider."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from little_agent.agent.agent import AgentCore
from little_agent.agent.nodes import AssistantNode, ToolResultNode, UserPromptNode
from little_agent.agent.session import SessionCore
from little_agent.agent.tool_manager import ToolManager
from little_agent.backends.protocol import BackendToolCall, BackendTurnResult
from little_agent.tools.protocol import ToolArgDef, ToolDef
from little_agent.tools.task import TASK_TIMEOUT, TaskToolProvider
from tests.mocks import MockBackend, MockClient, MockToolProvider


@pytest.fixture
def mock_session() -> MagicMock:
    """Minimal session mock sufficient for _task_dispatch (inheritance=False path)."""
    s = MagicMock()
    s.id = "mock-session-id"
    return s


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
async def test_task_basic(simple_agent: AgentCore, mock_session: MagicMock) -> None:
    """Task tool returns a completed result for a simple prompt."""
    provider = TaskToolProvider(simple_agent)
    result = await provider._task_dispatch({"prompt": "hello"}, mock_session)
    assert isinstance(result, dict)
    assert result["status"] == "completed"
    assert "output" in result


@pytest.mark.asyncio
async def test_task_missing_prompt(mock_session: MagicMock) -> None:
    """Task tool returns failed when prompt is absent or not a string."""
    agent = MagicMock()
    agent.tools.desc_tool.return_value = {}
    provider = TaskToolProvider(agent)
    result = await provider._task_dispatch({}, mock_session)
    assert isinstance(result, dict)
    assert result["status"] == "failed"


@pytest.mark.asyncio
async def test_task_timeout(simple_agent: AgentCore, mock_session: MagicMock) -> None:
    """Task tool returns timeout when asyncio.wait_for raises TimeoutError."""
    provider = TaskToolProvider(simple_agent)

    def _raise_timeout(coro: object, **_: object) -> None:
        if asyncio.iscoroutine(coro):
            coro.close()
        raise TimeoutError

    with patch("little_agent.tools.task.asyncio.wait_for", side_effect=_raise_timeout):
        result = await provider._task_dispatch({"prompt": "test"}, mock_session)

    assert isinstance(result, dict)
    assert result["status"] == "timeout"
    assert str(TASK_TIMEOUT) in str(result.get("output", ""))


@pytest.mark.asyncio
async def test_task_exception(simple_agent: AgentCore, mock_session: MagicMock) -> None:
    """Task tool returns failed when sub-session raises an unexpected error."""
    provider = TaskToolProvider(simple_agent)

    def _raise_runtime(coro: object, **_: object) -> None:
        if asyncio.iscoroutine(coro):
            coro.close()
        raise RuntimeError("boom")

    with patch("little_agent.tools.task.asyncio.wait_for", side_effect=_raise_runtime):
        result = await provider._task_dispatch({"prompt": "test"}, mock_session)

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
async def test_fork_for_inheritance_drops_tail_tool_result_node(
    simple_agent: AgentCore,
) -> None:
    """_fork_for_inheritance drops the tail ToolResultNode (the one being written)."""
    provider = TaskToolProvider(simple_agent)
    session = SessionCore(session_id="s1", cwd="/tmp", agent=simple_agent)
    user = UserPromptNode(id="u1", prompt="hi")
    tail = ToolResultNode(id="r1", results={})
    session.messages = [user, tail]

    sub = await provider._fork_for_inheritance(session)

    # tail ToolResultNode is dropped; user node is kept
    assert sub.messages == [user]


@pytest.mark.asyncio
async def test_fork_for_inheritance_adds_placeholder_for_tool_calls(
    simple_agent: AgentCore,
) -> None:
    """After dropping tail, a placeholder ToolResultNode is added to close open tool_use."""
    provider = TaskToolProvider(simple_agent)
    session = SessionCore(session_id="s1", cwd="/tmp", agent=simple_agent)
    user = UserPromptNode(id="u1", prompt="hi")
    asst = AssistantNode(id="a1", tool_calls={"call_1": {"tool_name": "task", "arguments": {}}})
    tail = ToolResultNode(id="r1", results={})
    session.messages = [user, asst, tail]

    sub = await provider._fork_for_inheritance(session)

    assert len(sub.messages) == 3
    assert sub.messages[0] is user
    assert sub.messages[1] is asst
    placeholder = sub.messages[2]
    assert isinstance(placeholder, ToolResultNode)
    assert "call_1" in placeholder.results
    assert placeholder.results["call_1"]["status"] == "completed"


@pytest.mark.asyncio
async def test_fork_for_inheritance_no_placeholder_without_tool_calls(
    simple_agent: AgentCore,
) -> None:
    """No placeholder is added when the preceding AssistantNode has no tool_calls."""
    provider = TaskToolProvider(simple_agent)
    session = SessionCore(session_id="s1", cwd="/tmp", agent=simple_agent)
    user = UserPromptNode(id="u1", prompt="hi")
    asst = AssistantNode(id="a1", text="reply")
    tail = ToolResultNode(id="r1", results={})
    session.messages = [user, asst, tail]

    sub = await provider._fork_for_inheritance(session)

    assert len(sub.messages) == 2
    assert sub.messages == [user, asst]


@pytest.mark.asyncio
async def test_fork_for_inheritance_preserves_full_history(
    simple_agent: AgentCore,
) -> None:
    """Full multi-turn history is preserved; only the active ToolResultNode is dropped."""
    provider = TaskToolProvider(simple_agent)
    session = SessionCore(session_id="s1", cwd="/tmp", agent=simple_agent)
    n1 = UserPromptNode(id="u1", prompt="turn 1")
    n2 = AssistantNode(id="a1", text="answer 1")
    n3 = UserPromptNode(id="u2", prompt="turn 2")
    n4 = AssistantNode(id="a2", tool_calls={"call_x": {"tool_name": "task", "arguments": {}}})
    active_result = ToolResultNode(id="r1", results={})
    session.messages = [n1, n2, n3, n4, active_result]

    sub = await provider._fork_for_inheritance(session)

    # n1..n4 kept; active_result dropped; placeholder added for call_x
    assert sub.messages[:4] == [n1, n2, n3, n4]
    assert isinstance(sub.messages[4], ToolResultNode)
    assert sub.messages[4] is not active_result
    assert "call_x" in sub.messages[4].results


# ---------------------------------------------------------------------------
# T4: fork mode produces valid Anthropic message format (no naked tool_use)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fork_for_inheritance_anthropic_format_valid(
    simple_agent: AgentCore,
) -> None:
    """Forked session messages convert to Anthropic format without naked tool_use blocks.

    Anthropic requires every tool_use in an assistant message to have a
    matching tool_result in the following user message. The placeholder
    ToolResultNode added by _fork_for_inheritance must satisfy this.
    """
    provider = TaskToolProvider(simple_agent)
    session = SessionCore(session_id="s1", cwd="/tmp", agent=simple_agent)
    user = UserPromptNode(id="u1", prompt="go")
    asst = AssistantNode(
        id="a1",
        tool_calls={
            "call_1": {"tool_name": "task", "arguments": {"prompt": "sub"}},
            "call_2": {"tool_name": "bash", "arguments": {"command": "ls"}},
        },
    )
    active_result = ToolResultNode(id="r1", results={})
    session.messages = [user, asst, active_result]

    sub = await provider._fork_for_inheritance(session)

    # Convert to Anthropic format
    messages: list[dict] = []
    for node in sub.messages:
        messages.extend(node.to_anthropic())

    # Collect all tool_use ids and all tool_result ids
    tool_use_ids: set[str] = set()
    tool_result_ids: set[str] = set()
    for msg in messages:
        content = msg.get("content", [])
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "tool_use":
                        tool_use_ids.add(block["id"])
                    elif block.get("type") == "tool_result":
                        tool_result_ids.add(block["tool_use_id"])

    assert tool_use_ids == {"call_1", "call_2"}, "all tool_use ids must be present"
    assert tool_use_ids == tool_result_ids, "every tool_use must have a matching tool_result"


# ---------------------------------------------------------------------------
# T4: new session mode (inheritance=False) starts with no history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_task_new_session_has_no_history(
    simple_agent: AgentCore, mock_session: MagicMock
) -> None:
    """New session mode creates a fresh session with no messages from the parent."""
    from unittest.mock import patch

    created_sessions: list = []
    original_new = simple_agent.new

    async def capturing_new(cwd: str | None = None):  # type: ignore[no-untyped-def]
        sess = await original_new(cwd=cwd)
        created_sessions.append(sess)
        return sess

    provider = TaskToolProvider(simple_agent)
    with patch.object(simple_agent, "new", side_effect=capturing_new):
        result = await provider._task_dispatch(
            {"prompt": "hello", "inheritance": False}, mock_session
        )

    assert result["status"] == "completed"
    assert len(created_sessions) == 1
    # The session starts with no pre-existing messages (UserPromptNode is added by prompt())
    sub = created_sessions[0]
    assert sub.summaries == []


# ---------------------------------------------------------------------------
# T68: CancelledError does not escape _run_scheduler; result_future is set
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scheduler_cancelled_sets_result_future(
    simple_agent: AgentCore, mock_session: MagicMock
) -> None:
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
    spec = _TaskSpec(
        task_id=None,
        depends=[],
        kwargs={"prompt": "hi"},
        session=mock_session,
        result_future=future,
    )
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


# ---------------------------------------------------------------------------
# Sub-task calls a tool and returns the data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_task_subtask_calls_tool_and_returns_data() -> None:
    """Sub-task executes a tool turn and its output is returned to the parent."""
    client = MockClient()

    # Script (shared backend, calls in order):
    # 1. Main turn: tool_call="task"
    # 2. Sub-session turn 1: tool_call="echo" (sub-task uses a tool)
    # 3. Sub-session turn 2: completed after echo result
    # 4. Main turn 2: completed after task result
    backend = MockBackend(
        script=[
            BackendTurnResult(
                output_text="",
                tool_calls=[
                    BackendToolCall(
                        call_id="t1",
                        tool_name="task",
                        arguments={"prompt": "use echo"},
                    )
                ],
                finish_reason="tool_call",
            ),
            BackendTurnResult(
                output_text="",
                tool_calls=[
                    BackendToolCall(
                        call_id="e1",
                        tool_name="echo",
                        arguments={"text": "sub-data"},
                    )
                ],
                finish_reason="tool_call",
            ),
            BackendTurnResult(
                output_text="sub-task done",
                tool_calls=[],
                finish_reason="completed",
            ),
            BackendTurnResult(
                output_text="main done",
                tool_calls=[],
                finish_reason="completed",
            ),
        ]
    )

    tools = ToolManager()
    tools.register(
        MockToolProvider(
            tools={
                "echo": ToolDef(desc="Echo", args=[ToolArgDef("text", "string", "text", True)]),
            },
            responses={"echo": "sub-data"},
        )
    )
    agent = AgentCore(client=client, backend=backend, tools=tools)
    task_provider = TaskToolProvider(agent)
    tools.register(task_provider)

    session = await agent.new()
    reason, _ = await session.prompt("go")

    assert reason == "end_turn"

    # The outer ToolResultNode must have the task call resolved as completed.
    tool_result_nodes = [n for n in session.messages if isinstance(n, ToolResultNode)]
    assert tool_result_nodes, "Expected at least one ToolResultNode in main session"
    task_result = tool_result_nodes[0].results.get("t1")
    assert task_result is not None
    assert task_result["status"] == "completed"
    # The tool fn returns {"status":..,"output":..} which is stored under "content".
    content = task_result.get("content") or {}
    assert "sub-task done" in str(content.get("output", ""))


# ---------------------------------------------------------------------------
# Sub-task tries to call the task tool — must be blocked
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_task_subtask_cannot_call_task_tool() -> None:
    """Sub-task's allowed_tools excludes 'task'; backend trying to call it gets failed."""
    client = MockClient()

    # Script:
    # 1. Main turn: tool_call="task"
    # 2. Sub-session turn 1: tries tool_call="task" (recursive!)
    # 3. Sub-session turn 2: completed (after seeing the failed tool result)
    # 4. Main turn 2: completed
    backend = MockBackend(
        script=[
            BackendTurnResult(
                output_text="",
                tool_calls=[
                    BackendToolCall(
                        call_id="outer",
                        tool_name="task",
                        arguments={"prompt": "recurse"},
                    )
                ],
                finish_reason="tool_call",
            ),
            BackendTurnResult(
                output_text="",
                tool_calls=[
                    BackendToolCall(
                        call_id="inner",
                        tool_name="task",
                        arguments={"prompt": "deeper"},
                    )
                ],
                finish_reason="tool_call",
            ),
            BackendTurnResult(
                output_text="sub done",
                tool_calls=[],
                finish_reason="completed",
            ),
            BackendTurnResult(
                output_text="main done",
                tool_calls=[],
                finish_reason="completed",
            ),
        ]
    )

    tools = ToolManager()
    agent = AgentCore(client=client, backend=backend, tools=tools)
    task_provider = TaskToolProvider(agent)
    tools.register(task_provider)

    session = await agent.new()
    reason, _ = await session.prompt("go")

    assert reason == "end_turn"

    # Find the sub-session's ToolResultNode for the inner "task" call.
    # It must be failed because "task" is excluded from allowed_tools.
    all_tool_results = [n for n in backend.sessions[-2].messages if isinstance(n, ToolResultNode)]
    assert all_tool_results, "Sub-session must have a ToolResultNode"
    inner_result = all_tool_results[0].results.get("inner")
    assert inner_result is not None, "Inner task call must have a result"
    assert inner_result["status"] == "failed", (
        f"Expected failed for recursive task call, got {inner_result['status']!r}"
    )


# ---------------------------------------------------------------------------
# inheritance=True: sub-task forks parent history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_task_inheritance_sub_session_carries_parent_history() -> None:
    """With inheritance=True the sub-session is forked from the parent, not a blank session."""
    client = MockClient()

    # Script:
    # 1. Main turn 1: completed (establishes some history)
    # 2. Main turn 2 call 1: tool_call="task" with inheritance=True
    # 3. Sub-session call: completed
    # 4. Main turn 2 call 2: completed
    backend = MockBackend(
        script=[
            BackendTurnResult(
                output_text="first reply",
                tool_calls=[],
                finish_reason="completed",
            ),
            BackendTurnResult(
                output_text="",
                tool_calls=[
                    BackendToolCall(
                        call_id="t1",
                        tool_name="task",
                        arguments={"prompt": "what was the first reply?", "inheritance": True},
                    )
                ],
                finish_reason="tool_call",
            ),
            BackendTurnResult(
                output_text="sub done",
                tool_calls=[],
                finish_reason="completed",
            ),
            BackendTurnResult(
                output_text="main done",
                tool_calls=[],
                finish_reason="completed",
            ),
        ]
    )

    tools = ToolManager()
    agent = AgentCore(client=client, backend=backend, tools=tools)
    task_provider = TaskToolProvider(agent)
    tools.register(task_provider)

    session = await agent.new()

    # Turn 1: establishes history
    reason1, _ = await session.prompt("first prompt")
    assert reason1 == "end_turn"

    # Turn 2: calls task with inheritance=True
    reason2, _ = await session.prompt("second prompt")
    assert reason2 == "end_turn"

    # The outer task call must have succeeded (not failed with "no current session context").
    outer_nodes = [n for n in session.messages if isinstance(n, ToolResultNode)]
    assert outer_nodes, "Expected ToolResultNode in main session"
    task_res = outer_nodes[0].results.get("t1")
    assert task_res is not None
    assert task_res["status"] == "completed", (
        f"Expected completed for inheritance task, got {task_res}"
    )

    # The sub-session (second-to-last backend call) must contain history from turn 1.
    # backend.sessions[-2] is the sub-session's call, [-1] is main turn 2 call 2.
    sub_session = backend.sessions[-2]
    sub_user_prompts = [n for n in sub_session.messages if isinstance(n, UserPromptNode)]
    assert any(n.prompt == "first prompt" for n in sub_user_prompts), (
        "Sub-session must contain the first turn's UserPromptNode when inheritance=True"
    )
