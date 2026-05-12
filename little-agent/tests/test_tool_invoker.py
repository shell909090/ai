"""Integration tests for _invoke_tools behavior in ToolInvoker."""

from __future__ import annotations

import pytest

from little_agent.agent.permissions import YesManChecker
from little_agent.agent.tool_invoker import _truncate_tool_result
from little_agent.backends.protocol import BackendToolCall, BackendTurnResult
from little_agent.types import JSONValue
from tests.mocks import BuiltinToolProvider, MockAgent, MockBackend, MockClient


class _DenyAllChecker:
    """Permission checker that always denies."""

    async def request_permission(
        self, session: object, kind: str, payload: dict[str, JSONValue]
    ) -> bool:
        return False


def _make_script_with_tool(
    tool_name: str, arguments: dict[str, JSONValue]
) -> list[BackendTurnResult]:
    return [
        BackendTurnResult(
            output_text="",
            tool_calls=[BackendToolCall(call_id="t1", tool_name=tool_name, arguments=arguments)],
            finish_reason="tool_call",
        ),
        BackendTurnResult(
            output_text="done",
            tool_calls=[],
            finish_reason="completed",
        ),
    ]


@pytest.mark.asyncio
async def test_tool_not_in_allowed_names_fails() -> None:
    """Tool not in allowed_names results in failed status with 'Tool not in allowed list'."""
    client = MockClient()
    provider = BuiltinToolProvider()
    backend = MockBackend(script=_make_script_with_tool("add", {"a": 1, "b": 2}))
    agent = MockAgent(backend=backend, tools=provider, client=client, permissions=YesManChecker())
    session = await agent.new()

    # Restrict allowed tools to only "echo", not "add"
    await session.prompt("hello", allowed_tools=["echo"])

    updates = [
        u for u in client.updates if u.type == "tool_call_update" and u.data.get("call_id") == "t1"
    ]
    assert updates, "Expected a tool_call_update for call_id 't1'"
    update = updates[0]
    assert update.data["status"] == "failed"
    assert "Tool not in allowed list" in str(update.data.get("content", ""))
    assert "add" in str(update.data.get("content", ""))


@pytest.mark.asyncio
async def test_tool_in_allowed_names_runs() -> None:
    """Tool present in allowed_names with YesManChecker runs successfully."""
    client = MockClient()
    provider = BuiltinToolProvider()
    backend = MockBackend(script=_make_script_with_tool("echo", {"text": "world"}))
    agent = MockAgent(backend=backend, tools=provider, client=client, permissions=YesManChecker())
    session = await agent.new()

    await session.prompt("hello", allowed_tools=["echo"])

    updates = [
        u for u in client.updates if u.type == "tool_call_update" and u.data.get("call_id") == "t1"
    ]
    assert updates, "Expected a tool_call_update for call_id 't1'"
    update = updates[0]
    assert update.data["status"] == "completed"
    assert update.data["content"] == "world"


@pytest.mark.asyncio
async def test_permission_denied_fails() -> None:
    """_DenyAllChecker causes tool call to fail with 'Permission denied'."""
    client = MockClient()
    provider = BuiltinToolProvider()
    backend = MockBackend(script=_make_script_with_tool("echo", {"text": "hi"}))
    agent = MockAgent(backend=backend, tools=provider, client=client, permissions=_DenyAllChecker())
    session = await agent.new()

    await session.prompt("hello")

    updates = [
        u for u in client.updates if u.type == "tool_call_update" and u.data.get("call_id") == "t1"
    ]
    assert updates, "Expected a tool_call_update for call_id 't1'"
    update = updates[0]
    assert update.data["status"] == "failed"
    assert "Permission denied" in str(update.data.get("content", ""))


# ---------------------------------------------------------------------------
# T76: _cancel_requested=True before gather → tools marked cancelled, not called
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_before_gather_marks_tools_cancelled_and_skips_execution() -> None:
    """When cancel requested before gather, tools are not executed and marked cancelled."""
    call_log: list[str] = []

    client = MockClient()
    backend = MockBackend(script=_make_script_with_tool("echo", {"text": "hello"}))

    # Custom tool that records calls so we can assert it wasn't invoked.
    from little_agent.tools.protocol import ToolArgDef, ToolDef

    class _RecordingToolProvider:
        def __iter__(self):  # type: ignore[override]
            async def _echo(args: dict[str, JSONValue]) -> JSONValue:
                call_log.append("echo_called")
                return args.get("text", "")

            yield (
                "echo",
                ToolDef(
                    desc="Echo",
                    args=[ToolArgDef(name="text", type="string", desc="text", required=True)],
                ),
                _echo,
            )

    agent = MockAgent(
        backend=backend,
        tools=_RecordingToolProvider(),
        client=client,
        permissions=YesManChecker(),
    )
    session = await agent.new()

    # Directly manipulate _cancel_requested after the session is created
    # but before the tool is invoked. We do this by intercepting _run_tool_gather.
    from little_agent.agent.tool_invoker import ToolInvoker

    original_gather = ToolInvoker._run_tool_gather

    async def _cancel_then_gather(self, allowed_calls, tool_result_node):  # type: ignore[override]
        # Set cancel flag immediately before delegating so that the guard fires.
        self._session._cancel_requested = True
        return await original_gather(self, allowed_calls, tool_result_node)

    ToolInvoker._run_tool_gather = _cancel_then_gather  # type: ignore[method-assign]
    try:
        await session.prompt("hello")
    finally:
        ToolInvoker._run_tool_gather = original_gather  # type: ignore[method-assign]

    # The actual tool function must not have been called.
    assert "echo_called" not in call_log, (
        "Tool function must not be called when _cancel_requested is True before gather"
    )

    # The tool result must carry 'cancelled' status.
    tool_updates = [
        u for u in client.updates if u.type == "tool_call_update" and u.data.get("call_id") == "t1"
    ]
    assert tool_updates, "Expected a tool_call_update for 't1'"
    assert tool_updates[0].data["status"] == "cancelled"


@pytest.mark.asyncio
async def test_no_allowed_names_grants_by_default() -> None:
    """When allowed_names is None and YesManChecker is used, tool runs successfully."""
    client = MockClient()
    provider = BuiltinToolProvider()
    backend = MockBackend(script=_make_script_with_tool("add", {"a": 3, "b": 4}))
    agent = MockAgent(backend=backend, tools=provider, client=client, permissions=YesManChecker())
    session = await agent.new()

    # _turn_allowed_tools is None by default → no restriction
    await session.prompt("hello")

    updates = [
        u for u in client.updates if u.type == "tool_call_update" and u.data.get("call_id") == "t1"
    ]
    assert updates, "Expected a tool_call_update for call_id 't1'"
    update = updates[0]
    assert update.data["status"] == "completed"
    assert update.data["content"] == 7


# ---------------------------------------------------------------------------
# Truncation: _truncate_tool_result unit tests
# ---------------------------------------------------------------------------


def test_truncate_tool_result_within_limit_unchanged() -> None:
    """Content within max_chars is returned as-is (same object)."""
    content: JSONValue = {"stdout": "hello", "returncode": 0}
    result = _truncate_tool_result(content, max_chars=1000)
    assert result == content


def test_truncate_tool_result_string_within_limit() -> None:
    """A short string is returned unchanged."""
    result = _truncate_tool_result("short", max_chars=100)
    assert result == "short"


def test_truncate_tool_result_over_limit_returns_string() -> None:
    """Content exceeding max_chars is serialized, truncated, and annotated."""
    big = "x" * 200
    result = _truncate_tool_result(big, max_chars=50)
    assert isinstance(result, str)
    assert "[TRUNCATED:" in result
    assert "chars total" in result  # annotation present


def test_truncate_tool_result_over_limit_prefix_length() -> None:
    """The returned string starts with exactly max_chars JSON-serialized chars."""
    content: JSONValue = {"body": "a" * 300}
    result = _truncate_tool_result(content, max_chars=20)
    assert isinstance(result, str)
    # First line is the truncated JSON prefix
    first_line = result.split("\n")[0]
    assert len(first_line) == 20


def test_truncate_tool_result_dict_over_limit() -> None:
    """A large dict is truncated and annotated."""
    big_dict: JSONValue = {"key": "v" * 1000}
    result = _truncate_tool_result(big_dict, max_chars=100)
    assert isinstance(result, str)
    assert "[TRUNCATED:" in result


def test_truncate_tool_result_list_over_limit() -> None:
    """A large list is truncated and annotated."""
    big_list: JSONValue = ["item"] * 500
    result = _truncate_tool_result(big_list, max_chars=100)
    assert isinstance(result, str)
    assert "[TRUNCATED:" in result


# ---------------------------------------------------------------------------
# Truncation: end-to-end via ToolInvoker
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_result_truncated_in_completed_update() -> None:
    """Large tool output is truncated before being stored and broadcast."""
    from little_agent.tools.protocol import ToolDef

    big_output = "z" * 10000

    class _BigOutputProvider:
        def __iter__(self):  # type: ignore[override]
            async def _big(args: dict[str, JSONValue]) -> JSONValue:
                return big_output

            yield (
                "big",
                ToolDef(desc="returns big output", args=[]),
                _big,
            )

    client = MockClient()
    backend = MockBackend(
        script=[
            BackendTurnResult(
                output_text="",
                tool_calls=[BackendToolCall(call_id="t1", tool_name="big", arguments={})],
                finish_reason="tool_call",
            ),
            BackendTurnResult(output_text="done", tool_calls=[], finish_reason="completed"),
        ]
    )
    agent = MockAgent(
        backend=backend,
        tools=_BigOutputProvider(),
        client=client,
        permissions=YesManChecker(),
        max_tool_result_chars=100,
    )
    session = await agent.new()
    await session.prompt("go")

    updates = [
        u for u in client.updates if u.type == "tool_call_update" and u.data.get("call_id") == "t1"
    ]
    assert updates, "Expected tool_call_update for t1"
    content = updates[0].data["content"]
    assert isinstance(content, str)
    assert "[TRUNCATED:" in str(content)
    assert len(str(content)) < 10000


@pytest.mark.asyncio
async def test_tool_result_not_truncated_when_within_limit() -> None:
    """Small tool output is stored verbatim when within max_tool_result_chars."""
    client = MockClient()
    provider = BuiltinToolProvider()
    backend = MockBackend(script=_make_script_with_tool("echo", {"text": "hi"}))
    agent = MockAgent(
        backend=backend,
        tools=provider,
        client=client,
        permissions=YesManChecker(),
        max_tool_result_chars=100,
    )
    session = await agent.new()
    await session.prompt("hello")

    updates = [
        u for u in client.updates if u.type == "tool_call_update" and u.data.get("call_id") == "t1"
    ]
    assert updates
    assert updates[0].data["content"] == "hi"
