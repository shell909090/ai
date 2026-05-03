"""Tests for task tool provider."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from little_agent.agent.core import AgentCore, SessionCore
from little_agent.agent.nodes import AssistantResponseNode, UserPromptNode
from little_agent.backends.protocol import BackendTurnResult
from little_agent.tools.manager import ToolManager
from little_agent.tools.task import TASK_TIMEOUT, TaskToolProvider
from tests.mocks import MockBackend, MockClient, MockToolProvider


@pytest.fixture
def simple_agent() -> AgentCore:
    """AgentCore backed by a single-shot MockBackend."""
    client = MockClient()
    backend = MockBackend(
        script=[BackendTurnResult(output_text="done", tool_calls=[], finish_reason="completed")]
    )
    tools = MockToolProvider(tools={"echo": ("Echo the input", [("text", "string", "text", True)])})
    return AgentCore(client=client, backend=backend, tools=tools)


def test_task_tool_list() -> None:
    """TaskToolProvider exposes create_task."""
    from unittest.mock import MagicMock

    agent = MagicMock()
    agent.tools.list.return_value = {}
    provider = TaskToolProvider(agent)
    tools = provider.list()
    assert "create_task" in tools


@pytest.mark.asyncio
async def test_task_tool_unknown_raises() -> None:
    """Invoking an unknown tool name raises ValueError."""
    from unittest.mock import MagicMock

    agent = MagicMock()
    agent.tools.list.return_value = {}
    provider = TaskToolProvider(agent)
    with pytest.raises(ValueError, match="Unknown tool"):
        await provider.invoke("nonexistent", {})


@pytest.mark.asyncio
async def test_create_task_basic(simple_agent: AgentCore) -> None:
    """create_task returns a completed result for a simple prompt."""
    provider = TaskToolProvider(simple_agent)
    result = await provider.invoke("create_task", {"prompt": "hello"})
    assert isinstance(result, dict)
    assert result["status"] == "completed"
    assert "output" in result


@pytest.mark.asyncio
async def test_create_task_missing_prompt() -> None:
    """create_task returns failed when prompt is absent or not a string."""
    from unittest.mock import MagicMock

    agent = MagicMock()
    agent.tools.list.return_value = {}
    provider = TaskToolProvider(agent)
    result = await provider.invoke("create_task", {})
    assert isinstance(result, dict)
    assert result["status"] == "failed"


@pytest.mark.asyncio
async def test_create_task_timeout(simple_agent: AgentCore) -> None:
    """create_task returns timeout when asyncio.wait_for raises TimeoutError."""
    provider = TaskToolProvider(simple_agent)

    def _raise_timeout(coro: object, **_: object) -> None:
        if asyncio.iscoroutine(coro):
            coro.close()
        raise TimeoutError

    with patch("little_agent.tools.task.asyncio.wait_for", side_effect=_raise_timeout):
        result = await provider.invoke("create_task", {"prompt": "test"})

    assert isinstance(result, dict)
    assert result["status"] == "timeout"
    assert str(TASK_TIMEOUT) in str(result.get("output", ""))


@pytest.mark.asyncio
async def test_create_task_exception(simple_agent: AgentCore) -> None:
    """create_task returns failed when sub-session raises an unexpected error."""
    provider = TaskToolProvider(simple_agent)

    def _raise_runtime(coro: object, **_: object) -> None:
        if asyncio.iscoroutine(coro):
            coro.close()
        raise RuntimeError("boom")

    with patch("little_agent.tools.task.asyncio.wait_for", side_effect=_raise_runtime):
        result = await provider.invoke("create_task", {"prompt": "test"})

    assert isinstance(result, dict)
    assert result["status"] == "failed"
    assert "boom" in str(result.get("output", ""))


def test_build_sub_tools_excludes_create_task(simple_agent: AgentCore) -> None:
    """Sub-task tool set never includes create_task (prevents recursion)."""
    mgr = ToolManager()
    mgr.register(MockToolProvider(tools={"echo": ("Echo", [("text", "string", "t", True)])}))
    provider = TaskToolProvider(simple_agent)
    mgr.register(provider)
    simple_agent.tools = mgr

    sub_tools = provider._build_sub_tools(None)
    assert "create_task" not in sub_tools.list()
    assert "echo" in sub_tools.list()


def test_build_sub_tools_filter_by_names(simple_agent: AgentCore) -> None:
    """Sub-task tool set is limited to the requested names."""
    mgr = ToolManager()
    mgr.register(
        MockToolProvider(
            tools={
                "echo": ("Echo", [("text", "string", "t", True)]),
                "add": ("Add", [("a", "number", "a", True), ("b", "number", "b", True)]),
            }
        )
    )
    provider = TaskToolProvider(simple_agent)
    simple_agent.tools = mgr

    sub_tools = provider._build_sub_tools(["echo"])
    assert "echo" in sub_tools.list()
    assert "add" not in sub_tools.list()
    assert "create_task" not in sub_tools.list()


@pytest.mark.asyncio
async def test_fork_for_inheritance_tail_none(simple_agent: AgentCore) -> None:
    """_fork_for_inheritance with tail=None returns session with tail=None."""
    provider = TaskToolProvider(simple_agent)
    session = SessionCore(session_id="s1", cwd="/tmp", agent=simple_agent)
    session.tail = None

    sub = await provider._fork_for_inheritance(session)

    assert sub.tail is None
    assert sub.id != session.id
    assert sub.cwd == session.cwd
    assert sub.agent is not None
    assert sub.agent is not session.agent


@pytest.mark.asyncio
async def test_fork_for_inheritance_tail_no_frozen(simple_agent: AgentCore) -> None:
    """_fork_for_inheritance with tail lacking frozen uses tail as fork point."""
    provider = TaskToolProvider(simple_agent)
    session = SessionCore(session_id="s1", cwd="/tmp", agent=simple_agent)
    node = UserPromptNode(id="n1", prev=None, prompt="hi")
    session.tail = node

    sub = await provider._fork_for_inheritance(session)

    assert sub.tail is node


@pytest.mark.asyncio
async def test_fork_for_inheritance_skips_frozen_nodes(simple_agent: AgentCore) -> None:
    """_fork_for_inheritance skips nodes that have a frozen attribute."""
    provider = TaskToolProvider(simple_agent)
    session = SessionCore(session_id="s1", cwd="/tmp", agent=simple_agent)

    # Create a chain: tail(frozen=True) -> prev(frozen=True) -> head(no frozen)
    head = UserPromptNode(id="head", prev=None, prompt="hi")
    mid = AssistantResponseNode(id="mid", prev=head, text="mid", frozen=True)
    tail = AssistantResponseNode(id="tail", prev=mid, text="tail", frozen=True)
    session.tail = tail

    sub = await provider._fork_for_inheritance(session)

    assert sub.tail is head


@pytest.mark.asyncio
async def test_fork_for_inheritance_partial_frozen(simple_agent: AgentCore) -> None:
    """_fork_for_inheritance stops at first node without frozen attribute."""
    provider = TaskToolProvider(simple_agent)
    session = SessionCore(session_id="s1", cwd="/tmp", agent=simple_agent)

    # Chain: tail(frozen=True) -> prev(no frozen) -> older(frozen=True)
    older = AssistantResponseNode(id="older", prev=None, text="older", frozen=True)
    prev = UserPromptNode(id="prev", prev=older, prompt="hi")
    tail = AssistantResponseNode(id="tail", prev=prev, text="tail", frozen=True)
    session.tail = tail

    sub = await provider._fork_for_inheritance(session)

    assert sub.tail is prev


@pytest.mark.asyncio
async def test_fork_for_inheritance_all_frozen(simple_agent: AgentCore) -> None:
    """_fork_for_inheritance returns None when all nodes have frozen."""
    provider = TaskToolProvider(simple_agent)
    session = SessionCore(session_id="s1", cwd="/tmp", agent=simple_agent)

    n1 = AssistantResponseNode(id="n1", prev=None, text="n1", frozen=True)
    n2 = AssistantResponseNode(id="n2", prev=n1, text="n2", frozen=True)
    session.tail = n2

    sub = await provider._fork_for_inheritance(session)

    assert sub.tail is None
