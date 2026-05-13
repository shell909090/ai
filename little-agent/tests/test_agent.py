"""Tests for agent core and session."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator
from typing import cast

import pytest

from little_agent.agent.agent import AgentCore
from little_agent.agent.exceptions import SessionBusyError
from little_agent.agent.nodes import ToolCallNode, UserPromptNode
from little_agent.agent.protocol import PromptReturn, SessionUpdate
from little_agent.agent.session import SessionCore
from little_agent.agent.turn_runner import MAX_TURN_ITERATIONS
from little_agent.backends.exceptions import ContextOverflowError
from little_agent.backends.protocol import BackendToolCall, BackendTurnResult
from little_agent.tools.protocol import ToolArgDef, ToolDef
from little_agent.types import JSONValue
from tests.mocks import MockBackend, MockClient, MockToolProvider


@pytest.mark.asyncio
async def test_single_turn_no_tools() -> None:
    """Test single turn without tool calls."""
    client = MockClient()
    backend = MockBackend(
        [
            BackendTurnResult(output_text="hello", tool_calls=[], finish_reason="completed"),
        ]
    )
    tools = MockToolProvider()
    agent = AgentCore(client=client, backend=backend, tools=tools)
    session = await agent.new()
    reason, text = await session.prompt("hi")
    assert reason == "end_turn"
    assert text == "hello"
    assert len(client.updates) == 1
    assert client.updates[0].type == "agent_message_chunk"


@pytest.mark.asyncio
async def test_single_tool_call() -> None:
    """Test a single tool call in one turn."""
    client = MockClient()
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
    tools = MockToolProvider(
        tools={"echo": ToolDef(desc="Echo", args=[ToolArgDef("text", "string", "text", True)])},
        responses={"echo": "echoed"},
    )
    agent = AgentCore(client=client, backend=backend, tools=tools)
    session = await agent.new()
    reason, text = await session.prompt("call echo")
    assert reason == "end_turn"
    assert text == "done"
    assert any(u.type == "tool_call" for u in client.updates)
    assert any(u.type == "tool_call_update" for u in client.updates)


@pytest.mark.asyncio
async def test_single_tool_call_with_output_text() -> None:
    """Test output_text is not lost when finish_reason is tool_call."""
    client = MockClient()
    backend = MockBackend(
        [
            BackendTurnResult(
                output_text="thinking...",
                tool_calls=[
                    BackendToolCall(call_id="c1", tool_name="echo", arguments={"text": "hi"})
                ],
                finish_reason="tool_call",
            ),
            BackendTurnResult(output_text="done", tool_calls=[], finish_reason="completed"),
        ]
    )
    tools = MockToolProvider(
        tools={"echo": ToolDef(desc="Echo", args=[ToolArgDef("text", "string", "text", True)])},
        responses={"echo": "echoed"},
    )
    agent = AgentCore(client=client, backend=backend, tools=tools)
    session = await agent.new()
    reason, text = await session.prompt("call echo")
    assert reason == "end_turn"
    assert text == "done"
    chunk_updates = [u for u in client.updates if u.type == "agent_message_chunk"]
    assert any(u.data.get("text") == "thinking..." for u in chunk_updates)


@pytest.mark.asyncio
async def test_multiple_parallel_tool_calls() -> None:
    """Test multiple parallel tool calls."""
    client = MockClient()
    backend = MockBackend(
        [
            BackendTurnResult(
                output_text="",
                tool_calls=[
                    BackendToolCall(call_id="c1", tool_name="echo", arguments={"text": "a"}),
                    BackendToolCall(call_id="c2", tool_name="add", arguments={"a": 1, "b": 2}),
                ],
                finish_reason="tool_call",
            ),
            BackendTurnResult(output_text="ok", tool_calls=[], finish_reason="completed"),
        ]
    )
    tools = MockToolProvider(
        tools={
            "echo": ToolDef(desc="Echo", args=[ToolArgDef("text", "string", "text", True)]),
            "add": ToolDef(
                desc="Add",
                args=[
                    ToolArgDef("a", "number", "a", True),
                    ToolArgDef("b", "number", "b", True),
                ],
            ),
        },
        responses={"echo": "a", "add": 3},
    )
    agent = AgentCore(client=client, backend=backend, tools=tools)
    session = await agent.new()
    reason, text = await session.prompt("parallel")
    assert reason == "end_turn"
    tool_updates = [u for u in client.updates if u.type == "tool_call_update"]
    assert len(tool_updates) == 2


@pytest.mark.asyncio
async def test_multi_turn_backend_tool_loop() -> None:
    """Test multi-turn backend-tool loop."""
    client = MockClient()
    backend = MockBackend(
        [
            BackendTurnResult(
                output_text="",
                tool_calls=[
                    BackendToolCall(call_id="c1", tool_name="echo", arguments={"text": "x"})
                ],
                finish_reason="tool_call",
            ),
            BackendTurnResult(
                output_text="",
                tool_calls=[
                    BackendToolCall(call_id="c2", tool_name="echo", arguments={"text": "y"})
                ],
                finish_reason="tool_call",
            ),
            BackendTurnResult(output_text="final", tool_calls=[], finish_reason="completed"),
        ]
    )
    tools = MockToolProvider(
        tools={"echo": ToolDef(desc="Echo", args=[ToolArgDef("text", "string", "text", True)])},
        responses={"echo": "ok"},
    )
    agent = AgentCore(client=client, backend=backend, tools=tools)
    session = await agent.new()
    reason, text = await session.prompt("loop")
    assert reason == "end_turn"
    assert text == "final"


@pytest.mark.asyncio
async def test_tool_exception_captured() -> None:
    """Test tool exception is captured, not raised."""
    client = MockClient()
    backend = MockBackend(
        [
            BackendTurnResult(
                output_text="",
                tool_calls=[BackendToolCall(call_id="c1", tool_name="bad", arguments={})],
                finish_reason="tool_call",
            ),
            BackendTurnResult(output_text="recovered", tool_calls=[], finish_reason="completed"),
        ]
    )
    tools = MockToolProvider(
        tools={"bad": ToolDef(desc="Bad tool", args=[])},
        errors={"bad"},
    )
    agent = AgentCore(client=client, backend=backend, tools=tools)
    session = await agent.new()
    reason, text = await session.prompt("fail")
    assert reason == "end_turn"
    assert text == "recovered"


@pytest.mark.asyncio
async def test_cancel_during_tool_execution() -> None:
    """Test cancel during tool execution."""
    client = MockClient()

    async def slow_generate(
        session: object,
    ) -> AsyncGenerator[SessionUpdate | BackendTurnResult, None]:
        await asyncio.sleep(0.5)
        yield BackendTurnResult(
            output_text="",
            tool_calls=[BackendToolCall(call_id="c1", tool_name="echo", arguments={})],
            finish_reason="tool_call",
        )

    backend = MockBackend()
    backend.set_generate_fn(slow_generate)
    tools = MockToolProvider(
        tools={"echo": ToolDef(desc="Echo", args=[])}, responses={"echo": "ok"}
    )
    agent = AgentCore(client=client, backend=backend, tools=tools)
    session = await agent.new()

    result: PromptReturn | None = None

    async def prompt_task() -> None:
        nonlocal result
        result = await session.prompt("cancel me")

    task = asyncio.create_task(prompt_task())
    await asyncio.sleep(0.1)
    await session.cancel()
    await task
    assert result is not None
    assert result[0] == "cancelled"


@pytest.mark.asyncio
async def test_fork_shares_history() -> None:
    """Test fork creates new session sharing frozen history."""
    client = MockClient()
    backend = MockBackend(
        [
            BackendTurnResult(output_text="first", tool_calls=[], finish_reason="completed"),
        ]
    )
    tools = MockToolProvider()
    agent = AgentCore(client=client, backend=backend, tools=tools)
    session = await agent.new()
    await session.prompt("hi")
    new_session = await session.fork()
    assert new_session.id != session.id
    assert new_session.tail is not None


@pytest.mark.asyncio
async def test_fork_during_active_turn_raises() -> None:
    """Test fork during active turn raises RuntimeError."""
    client = MockClient()

    async def slow_generate(
        session: object,
    ) -> AsyncGenerator[SessionUpdate | BackendTurnResult, None]:
        await asyncio.sleep(1.0)
        yield BackendTurnResult(output_text="", tool_calls=[], finish_reason="completed")

    backend = MockBackend()
    backend.set_generate_fn(slow_generate)
    tools = MockToolProvider()
    agent = AgentCore(client=client, backend=backend, tools=tools)
    session = await agent.new()
    task = asyncio.create_task(session.prompt("slow"))
    await asyncio.sleep(0.1)
    with pytest.raises(RuntimeError):
        await session.fork()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_compress_during_active_turn_raises() -> None:
    """Test compress during active turn raises RuntimeError."""
    client = MockClient()

    async def slow_generate(
        session: object,
    ) -> AsyncGenerator[SessionUpdate | BackendTurnResult, None]:
        await asyncio.sleep(1.0)
        yield BackendTurnResult(output_text="", tool_calls=[], finish_reason="completed")

    backend = MockBackend()
    backend.set_generate_fn(slow_generate)
    tools = MockToolProvider()
    agent = AgentCore(client=client, backend=backend, tools=tools)
    session = await agent.new()
    task = asyncio.create_task(session.prompt("slow"))
    await asyncio.sleep(0.1)
    with pytest.raises(RuntimeError):
        await session.compress()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_pending_queue_full_raises() -> None:
    """Test pending queue full raises SessionBusyError."""
    client = MockClient()

    async def slow_generate(
        session: object,
    ) -> AsyncGenerator[SessionUpdate | BackendTurnResult, None]:
        await asyncio.sleep(2.0)
        yield BackendTurnResult(output_text="", tool_calls=[], finish_reason="completed")

    backend = MockBackend()
    backend.set_generate_fn(slow_generate)
    tools = MockToolProvider()
    agent = AgentCore(client=client, backend=backend, tools=tools)
    session = await agent.new()
    task1 = asyncio.create_task(session.prompt("first"))
    await asyncio.sleep(0.05)
    task2 = asyncio.create_task(session.prompt("second"))
    await asyncio.sleep(0.05)
    task3 = asyncio.create_task(session.prompt("third"))
    await asyncio.sleep(0.05)
    task4 = asyncio.create_task(session.prompt("fourth"))
    await asyncio.sleep(0.05)
    with pytest.raises(SessionBusyError):
        await session.prompt("fifth")
    task1.cancel()
    task2.cancel()
    task3.cancel()
    task4.cancel()
    for t in (task1, task2, task3, task4):
        try:
            await t
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_pending_queue_executes_serially() -> None:
    """Test pending prompts are executed serially after active turn."""
    client = MockClient()
    backend = MockBackend(
        [
            BackendTurnResult(output_text="a", tool_calls=[], finish_reason="completed"),
            BackendTurnResult(output_text="b", tool_calls=[], finish_reason="completed"),
        ]
    )
    tools = MockToolProvider()
    agent = AgentCore(client=client, backend=backend, tools=tools)
    session = await agent.new()

    task1 = asyncio.create_task(session.prompt("first"))
    await asyncio.sleep(0.01)
    task2 = asyncio.create_task(session.prompt("second"))

    reason1, text1 = await task1
    reason2, text2 = await task2

    assert reason1 == "end_turn"
    assert text1 == "a"
    assert reason2 == "end_turn"
    assert text2 == "b"


@pytest.mark.asyncio
async def test_max_turn_iterations_exceeded() -> None:
    """Test max turn iterations exceeded raises RuntimeError."""
    client = MockClient()
    script = [
        BackendTurnResult(
            output_text="",
            tool_calls=[BackendToolCall(call_id=f"c{i}", tool_name="echo", arguments={})],
            finish_reason="tool_call",
        )
        for i in range(25)
    ]
    backend = MockBackend(script)
    tools = MockToolProvider(
        tools={"echo": ToolDef(desc="Echo", args=[])}, responses={"echo": "ok"}
    )
    agent = AgentCore(client=client, backend=backend, tools=tools)
    session = await agent.new()
    with pytest.raises(RuntimeError, match="Max turn iterations exceeded"):
        await session.prompt("loop")


@pytest.mark.asyncio
async def test_cancel_when_not_active() -> None:
    """Test cancel when no active turn does nothing."""
    client = MockClient()
    backend = MockBackend()
    tools = MockToolProvider()
    agent = AgentCore(client=client, backend=backend, tools=tools)
    session = await agent.new()
    await session.cancel()
    saved = session.save()
    assert isinstance(saved, dict)
    assert not saved.get("chain")


@pytest.mark.asyncio
async def test_compress_with_compressor() -> None:
    """Test compress with compressor configured."""
    client = MockClient()
    backend = MockBackend()
    tools = MockToolProvider()

    from little_agent.agent.nodes import Node

    class FakeCompressor:
        async def compress(self, head: Node | None) -> Node | None:
            return head

    agent = AgentCore(client=client, backend=backend, tools=tools, compressor=FakeCompressor())
    session = await agent.new()
    await session.compress()


@pytest.mark.asyncio
async def test_compress_no_compressor_raises() -> None:
    """Test compress without compressor raises RuntimeError."""
    client = MockClient()
    backend = MockBackend()
    tools = MockToolProvider()
    agent = AgentCore(client=client, backend=backend, tools=tools)
    session = await agent.new()
    with pytest.raises(RuntimeError, match="No compressor configured"):
        await session.compress()


@pytest.mark.asyncio
async def test_save_returns_dict_with_chain() -> None:
    """Test save returns session data with chain."""
    client = MockClient()
    backend = MockBackend(
        [
            BackendTurnResult(output_text="hello", tool_calls=[], finish_reason="completed"),
        ]
    )
    tools = MockToolProvider()
    agent = AgentCore(client=client, backend=backend, tools=tools)
    session = await agent.new()
    await session.prompt("hi")
    result = session.save()
    assert isinstance(result, dict)
    assert result["id"] == session.id
    assert "chain" in result
    assert len(result["chain"]) == 2  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_agent_load() -> None:
    """Test AgentCore.load restores session from data."""
    client = MockClient()
    backend = MockBackend()
    tools = MockToolProvider()
    agent = AgentCore(client=client, backend=backend, tools=tools)
    session = await agent.load({"id": "test-id", "cwd": "/tmp"})
    assert session.id == "test-id"
    assert session.cwd == "/tmp"


@pytest.mark.asyncio
async def test_agent_load_invalid_data_raises() -> None:
    """Test AgentCore.load with invalid data raises ValueError."""
    client = MockClient()
    backend = MockBackend()
    tools = MockToolProvider()
    agent = AgentCore(client=client, backend=backend, tools=tools)
    with pytest.raises(ValueError, match="Invalid session data"):
        await agent.load("not a dict")


@pytest.mark.asyncio
async def test_agent_load_missing_id_raises() -> None:
    """Test AgentCore.load with missing id raises ValueError."""
    client = MockClient()
    backend = MockBackend()
    tools = MockToolProvider()
    agent = AgentCore(client=client, backend=backend, tools=tools)
    with pytest.raises(ValueError, match="Session data missing 'id'"):
        await agent.load({"cwd": "/tmp"})


@pytest.mark.asyncio
async def test_agent_load_with_chain() -> None:
    """Test AgentCore.load restores chain."""
    client = MockClient()
    backend = MockBackend()
    tools = MockToolProvider()
    agent = AgentCore(client=client, backend=backend, tools=tools)
    data: JSONValue = {
        "id": "test-id",
        "cwd": "/tmp",
        "chain": [
            {"kind": "user_prompt", "id": "n1", "prompt": "hello"},
            {"kind": "assistant_response", "id": "n2", "text": "hi"},
        ],
    }
    session = await agent.load(data)
    session_core = cast(SessionCore, session)
    assert session_core.id == "test-id"
    assert session_core.tail is not None
    assert session_core.tail.kind == "assistant_response"
    assert session_core.tail.text == "hi"
    assert session_core.tail.prev is not None
    assert session_core.tail.prev.kind == "user_prompt"
    assert session_core.tail.prev.prompt == "hello"


@pytest.mark.asyncio
async def test_save_load_round_trip() -> None:
    """Test save and load round-trip."""
    client = MockClient()
    backend = MockBackend(
        [
            BackendTurnResult(output_text="hello", tool_calls=[], finish_reason="completed"),
        ]
    )
    tools = MockToolProvider()
    agent = AgentCore(client=client, backend=backend, tools=tools)
    session = await agent.new()
    await session.prompt("hi")
    saved = session.save()

    loaded_session = await agent.load(saved)
    loaded_core = cast(SessionCore, loaded_session)
    original_core = cast(SessionCore, session)
    assert loaded_core.id == original_core.id
    assert loaded_core.cwd == original_core.cwd
    assert loaded_core.tail is not None
    assert loaded_core.tail.kind == "assistant_response"
    assert loaded_core.tail.text == "hello"


@pytest.mark.asyncio
async def test_thinking_chunk_emitted_when_thinking_text_present() -> None:
    """Test thinking_chunk update is emitted when backend returns thinking_text."""
    client = MockClient()
    backend = MockBackend(
        [
            BackendTurnResult(
                output_text="answer",
                tool_calls=[],
                finish_reason="completed",
                thinking_text="I am thinking...",
            ),
        ]
    )
    tools = MockToolProvider()
    agent = AgentCore(client=client, backend=backend, tools=tools)
    session = await agent.new()
    reason, text = await session.prompt("hi")
    assert reason == "end_turn"
    assert text == "answer"
    thinking_updates = [u for u in client.updates if u.type == "thinking_chunk"]
    assert len(thinking_updates) == 1
    assert thinking_updates[0].data.get("text") == "I am thinking..."


# ===========================================================================
# T39 tests
# ===========================================================================


def test_max_turn_iterations_is_20() -> None:
    """MAX_TURN_ITERATIONS must equal 20 per §8."""
    assert MAX_TURN_ITERATIONS == 20


@pytest.mark.asyncio
async def test_post_turn_compress_triggered_by_token_ratio() -> None:
    """Token usage ratio > R schedules post-turn compress."""
    compress_calls: list[object] = []

    class _TrackingCompressor:
        async def compress(self, tail):
            compress_calls.append(tail)
            return tail

    backend = MockBackend(
        [
            BackendTurnResult(
                output_text="hi",
                tool_calls=[],
                finish_reason="completed",
                usage={"input_tokens": 70000, "output_tokens": 70000},
            )
        ]
    )
    agent = AgentCore(
        client=MockClient(),
        backend=backend,
        tools=MockToolProvider(),
        compressor=_TrackingCompressor(),
        compress_threshold=0.5,
        context_window=128000,
    )
    session = await agent.new()
    await session.prompt("hi")

    # Allow the background compress task to run
    await asyncio.sleep(0.05)
    assert len(compress_calls) == 1


@pytest.mark.asyncio
async def test_post_turn_compress_not_triggered_below_threshold() -> None:
    """Token usage ratio <= R does not schedule compress."""
    compress_calls: list[object] = []

    class _TrackingCompressor:
        async def compress(self, tail):
            compress_calls.append(tail)
            return tail

    backend = MockBackend(
        [
            BackendTurnResult(
                output_text="hi",
                tool_calls=[],
                finish_reason="completed",
                usage={"input_tokens": 10000, "output_tokens": 10000},
            )
        ]
    )
    agent = AgentCore(
        client=MockClient(),
        backend=backend,
        tools=MockToolProvider(),
        compressor=_TrackingCompressor(),
        compress_threshold=0.5,
        context_window=128000,
    )
    session = await agent.new()
    await session.prompt("hi")
    await asyncio.sleep(0.05)
    assert len(compress_calls) == 0


@pytest.mark.asyncio
async def test_post_turn_compress_char_fallback_when_usage_none() -> None:
    """Char fallback triggers compress when usage is None and chain is large."""
    compress_calls: list[object] = []

    class _TrackingCompressor:
        async def compress(self, tail):
            compress_calls.append(tail)
            return tail

    backend = MockBackend(
        [
            BackendTurnResult(
                output_text="x" * 2000,  # large response, no usage
                tool_calls=[],
                finish_reason="completed",
                usage=None,
            )
        ]
    )
    # Small context_window so char count triggers easily
    agent = AgentCore(
        client=MockClient(),
        backend=backend,
        tools=MockToolProvider(),
        compressor=_TrackingCompressor(),
        compress_threshold=0.5,
        context_window=100,  # very small: char/4 easily > 50
    )
    session = await agent.new()
    await session.prompt("hello")
    await asyncio.sleep(0.05)
    assert len(compress_calls) == 1


@pytest.mark.asyncio
async def test_post_turn_compress_char_fallback_when_usage_zero() -> None:
    """Char fallback triggers compress when usage fields are both 0."""
    compress_calls: list[object] = []

    class _TrackingCompressor:
        async def compress(self, tail):
            compress_calls.append(tail)
            return tail

    backend = MockBackend(
        [
            BackendTurnResult(
                output_text="x" * 2000,
                tool_calls=[],
                finish_reason="completed",
                usage={"input_tokens": 0, "output_tokens": 0},
            )
        ]
    )
    agent = AgentCore(
        client=MockClient(),
        backend=backend,
        tools=MockToolProvider(),
        compressor=_TrackingCompressor(),
        compress_threshold=0.5,
        context_window=100,
    )
    session = await agent.new()
    await session.prompt("hello")
    await asyncio.sleep(0.05)
    assert len(compress_calls) == 1


@pytest.mark.asyncio
async def test_post_turn_compress_r_boundary_not_triggered() -> None:
    """Ratio equal to R does NOT trigger (strictly greater-than check)."""
    compress_calls: list[object] = []

    class _TrackingCompressor:
        async def compress(self, tail):
            compress_calls.append(tail)
            return tail

    # ratio = 64000 / 128000 = 0.5, R = 0.5 → ratio > R is False
    backend = MockBackend(
        [
            BackendTurnResult(
                output_text="ok",
                tool_calls=[],
                finish_reason="completed",
                usage={"input_tokens": 32000, "output_tokens": 32000},
            )
        ]
    )
    agent = AgentCore(
        client=MockClient(),
        backend=backend,
        tools=MockToolProvider(),
        compressor=_TrackingCompressor(),
        compress_threshold=0.5,
        context_window=128000,
    )
    session = await agent.new()
    await session.prompt("hi")
    await asyncio.sleep(0.05)
    assert len(compress_calls) == 0


@pytest.mark.asyncio
async def test_compress_task_holds_pending_queue() -> None:
    """Post-turn compress holds _active_turn; second prompt waits until compress finishes."""
    compress_started = asyncio.Event()
    compress_release = asyncio.Event()

    class _SlowCompressor:
        async def compress(self, tail):
            compress_started.set()
            await compress_release.wait()
            return tail

    backend = MockBackend(
        [
            BackendTurnResult(
                output_text="first",
                tool_calls=[],
                finish_reason="completed",
                usage={"input_tokens": 100000, "output_tokens": 100000},
            ),
            BackendTurnResult(output_text="second", tool_calls=[], finish_reason="completed"),
        ]
    )
    agent = AgentCore(
        client=MockClient(),
        backend=backend,
        tools=MockToolProvider(),
        compressor=_SlowCompressor(),
        compress_threshold=0.5,
        context_window=128000,
    )
    session = await agent.new()

    task1 = asyncio.create_task(session.prompt("first"))
    result1 = await task1
    assert result1 == ("end_turn", "first")

    await compress_started.wait()
    # Cast to SessionCore to inspect internal state: _active_turn is held by compress task.
    assert cast(SessionCore, session)._active_turn is True

    task2 = asyncio.create_task(session.prompt("second"))
    await asyncio.sleep(0.01)
    assert not task2.done()

    compress_release.set()
    result2 = await task2
    assert result2 == ("end_turn", "second")


@pytest.mark.asyncio
async def test_in_turn_overflow_retry_success() -> None:
    """ContextOverflowError on first backend call triggers compress+retry; retry succeeds."""

    class _OverflowOnceThenSucceed:
        def __init__(self) -> None:
            self.calls = 0

        def generate(self, session: object):
            return self._gen()

        async def _gen(self):
            self.calls += 1
            if self.calls == 1:
                raise ContextOverflowError("too long")
                yield  # pragma: no cover
            yield BackendTurnResult(
                output_text="ok after retry", tool_calls=[], finish_reason="completed"
            )

    class _MinimalCompressor:
        async def compress(self, tail):
            import dataclasses

            return dataclasses.replace(tail)  # new object signals compression ran

    backend = _OverflowOnceThenSucceed()
    agent = AgentCore(
        client=MockClient(),
        backend=backend,  # type: ignore[arg-type]
        tools=MockToolProvider(),
        compressor=_MinimalCompressor(),
        compress_threshold=0.99,
        context_window=128000,
    )
    session = await agent.new()
    reason, text = await session.prompt("hi")
    assert reason == "end_turn"
    assert text == "ok after retry"
    assert backend.calls == 2


@pytest.mark.asyncio
async def test_in_turn_overflow_second_raises() -> None:
    """ContextOverflowError on retry propagates to caller."""

    class _AlwaysOverflow:
        def generate(self, session: object):
            return self._gen()

        async def _gen(self):
            raise ContextOverflowError("always too long")
            yield  # pragma: no cover

    class _NoopCompressor:
        async def compress(self, tail):
            return tail

    agent = AgentCore(
        client=MockClient(),
        backend=_AlwaysOverflow(),  # type: ignore[arg-type]
        tools=MockToolProvider(),
        compressor=_NoopCompressor(),
        compress_threshold=0.99,
        context_window=128000,
    )
    session = await agent.new()
    with pytest.raises(ContextOverflowError):
        await session.prompt("hi")


# ---------------------------------------------------------------------------
# T74: streaming backend does not re-send chunks via _handle_completed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_streaming_backend_no_duplicate_agent_message_chunk() -> None:
    """_handle_completed must NOT emit agent_message_chunk when backend already streamed.

    When the backend yields agent_message_chunk updates during generate(),
    `did_stream` is True and `_handle_completed` must skip the final
    full-text re-emit. The client must receive each chunk exactly once.
    """
    client = MockClient()
    tools = MockToolProvider()

    # Build a backend that streams chunks followed by a BackendTurnResult.
    class _StreamingBackend:
        async def generate(
            self, session: object
        ) -> AsyncIterator[SessionUpdate | BackendTurnResult]:
            yield SessionUpdate(type="agent_message_chunk", data={"text": "Hello "})  # type: ignore[misc]
            yield SessionUpdate(type="agent_message_chunk", data={"text": "world"})  # type: ignore[misc]
            yield BackendTurnResult(  # type: ignore[misc]
                output_text="Hello world",
                tool_calls=[],
                finish_reason="completed",
            )

    agent = AgentCore(client=client, backend=_StreamingBackend(), tools=tools)  # type: ignore[arg-type]
    session = await agent.new()
    reason, text = await session.prompt("hi")

    assert reason == "end_turn"
    assert text == "Hello world"

    # Collect all agent_message_chunk updates.
    chunk_updates = [u for u in client.updates if u.type == "agent_message_chunk"]

    # Exactly two streaming chunks — the full-text re-emit must NOT be present.
    chunk_texts = [u.data.get("text") for u in chunk_updates]
    assert "Hello world" not in chunk_texts or chunk_texts.count("Hello world") == 0, (
        f"Full text re-emit must be suppressed when streaming; got: {chunk_texts}"
    )
    # The two streamed chunks must be present.
    full_text = "".join(str(t) for t in chunk_texts)
    assert full_text == "Hello world", (
        f"Concatenated streamed chunks must equal the full text; got: {chunk_texts!r}"
    )


@pytest.mark.asyncio
async def test_cancel_interrupts_compress_task() -> None:
    """cancel() during post-turn compress cancels the task and clears _active_turn."""
    compress_started = asyncio.Event()
    cancelled_flag: list[bool] = []

    class _SlowCompressor:
        async def compress(self, tail):
            compress_started.set()
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cancelled_flag.append(True)
                raise
            return tail

    backend = MockBackend(
        [
            BackendTurnResult(
                output_text="done",
                tool_calls=[],
                finish_reason="completed",
                usage={"input_tokens": 100000, "output_tokens": 100000},
            )
        ]
    )
    agent = AgentCore(
        client=MockClient(),
        backend=backend,
        tools=MockToolProvider(),
        compressor=_SlowCompressor(),
        compress_threshold=0.5,
        context_window=128000,
    )
    session = await agent.new()
    result = await session.prompt("hi")
    assert result[0] == "end_turn"

    await compress_started.wait()
    # Cast to SessionCore to inspect internal state: _active_turn is held by compress task.
    assert cast(SessionCore, session)._active_turn is True

    await session.cancel()
    await asyncio.sleep(0.1)

    # Cast to SessionCore to verify _active_turn is cleared after cancel.
    assert cast(SessionCore, session)._active_turn is False
    assert len(cancelled_flag) == 1 and cancelled_flag[0] is True


# ---------------------------------------------------------------------------
# ToolCallNode.output_text serialization round-trip
# ---------------------------------------------------------------------------


def test_tool_call_node_output_text_preserved_in_chain() -> None:
    """ToolCallNode.output_text survives to_dict / from_dict round-trip."""
    prev = UserPromptNode(id="n0", prev=None, prompt="go")
    node = ToolCallNode(
        id="n1",
        prev=prev,
        output_text="I will use bash",
        calls={"c1": {"tool_name": "bash", "arguments": {"cmd": "ls"}}},
    )

    serialized = node.to_dict()
    assert serialized.get("output_text") == "I will use bash"

    restored = ToolCallNode.from_dict(serialized, prev=prev)
    assert isinstance(restored, ToolCallNode)
    assert restored.output_text == "I will use bash"
    assert restored.calls == node.calls
