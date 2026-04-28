"""Tests for agent core and session."""

import asyncio

import pytest

from little_agent.agent.core import AgentCore
from little_agent.agent.exceptions import SessionBusyError
from little_agent.backends.protocol import BackendToolCall, BackendTurnResult
from tests.mocks import MockBackend, MockClient, MockToolManager


@pytest.mark.asyncio
async def test_single_turn_no_tools() -> None:
    """Test single turn without tool calls."""
    client = MockClient()
    backend = MockBackend(
        [
            BackendTurnResult(output_text="hello", tool_calls=[], finish_reason="completed"),
        ]
    )
    tools = MockToolManager()
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
    tools = MockToolManager(
        tools={"echo": ("Echo", [("text", "string", "text", True)])},
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
    tools = MockToolManager(
        tools={
            "echo": ("Echo", [("text", "string", "text", True)]),
            "add": ("Add", [("a", "number", "a", True), ("b", "number", "b", True)]),
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
    tools = MockToolManager(
        tools={"echo": ("Echo", [("text", "string", "text", True)])},
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
    tools = MockToolManager(
        tools={"bad": ("Bad tool", [])},
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

    async def slow_generate(session: object) -> BackendTurnResult:
        await asyncio.sleep(0.5)
        return BackendTurnResult(
            output_text="",
            tool_calls=[BackendToolCall(call_id="c1", tool_name="echo", arguments={})],
            finish_reason="tool_call",
        )

    backend = MockBackend()
    backend.generate = slow_generate  # type: ignore[method-assign]
    tools = MockToolManager(tools={"echo": ("Echo", [])}, responses={"echo": "ok"})
    agent = AgentCore(client=client, backend=backend, tools=tools)
    session = await agent.new()

    async def prompt_task() -> None:
        await session.prompt("cancel me")

    task = asyncio.create_task(prompt_task())
    await asyncio.sleep(0.1)
    await session.cancel()
    await task


@pytest.mark.asyncio
async def test_fork_shares_history() -> None:
    """Test fork creates new session sharing frozen history."""
    client = MockClient()
    backend = MockBackend(
        [
            BackendTurnResult(output_text="first", tool_calls=[], finish_reason="completed"),
        ]
    )
    tools = MockToolManager()
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

    async def slow_generate(session: object) -> BackendTurnResult:
        await asyncio.sleep(1.0)
        return BackendTurnResult(output_text="", tool_calls=[], finish_reason="completed")

    backend = MockBackend()
    backend.generate = slow_generate  # type: ignore[method-assign]
    tools = MockToolManager()
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

    async def slow_generate(session: object) -> BackendTurnResult:
        await asyncio.sleep(1.0)
        return BackendTurnResult(output_text="", tool_calls=[], finish_reason="completed")

    backend = MockBackend()
    backend.generate = slow_generate  # type: ignore[method-assign]
    tools = MockToolManager()
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

    async def slow_generate(session: object) -> BackendTurnResult:
        await asyncio.sleep(2.0)
        return BackendTurnResult(output_text="", tool_calls=[], finish_reason="completed")

    backend = MockBackend()
    backend.generate = slow_generate  # type: ignore[method-assign]
    tools = MockToolManager()
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
    tools = MockToolManager()
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
        for i in range(15)
    ]
    backend = MockBackend(script)
    tools = MockToolManager(tools={"echo": ("Echo", [])}, responses={"echo": "ok"})
    agent = AgentCore(client=client, backend=backend, tools=tools)
    session = await agent.new()
    with pytest.raises(RuntimeError, match="Max turn iterations exceeded"):
        await session.prompt("loop")


@pytest.mark.asyncio
async def test_cancel_when_not_active() -> None:
    """Test cancel when no active turn does nothing."""
    client = MockClient()
    backend = MockBackend()
    tools = MockToolManager()
    agent = AgentCore(client=client, backend=backend, tools=tools)
    session = await agent.new()
    await session.cancel()
    assert not session.save().get("chain")


@pytest.mark.asyncio
async def test_compress_with_compressor() -> None:
    """Test compress with compressor configured."""
    client = MockClient()
    backend = MockBackend()
    tools = MockToolManager()

    class FakeCompressor:
        async def compress(self, head):
            return head

    agent = AgentCore(client=client, backend=backend, tools=tools, compressor=FakeCompressor())
    session = await agent.new()
    await session.compress()


@pytest.mark.asyncio
async def test_compress_no_compressor_raises() -> None:
    """Test compress without compressor raises RuntimeError."""
    client = MockClient()
    backend = MockBackend()
    tools = MockToolManager()
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
    tools = MockToolManager()
    agent = AgentCore(client=client, backend=backend, tools=tools)
    session = await agent.new()
    await session.prompt("hi")
    result = session.save()
    assert isinstance(result, dict)
    assert result["id"] == session.id
    assert "chain" in result
    assert len(result["chain"]) == 2


@pytest.mark.asyncio
async def test_agent_load() -> None:
    """Test AgentCore.load restores session from data."""
    client = MockClient()
    backend = MockBackend()
    tools = MockToolManager()
    agent = AgentCore(client=client, backend=backend, tools=tools)
    session = await agent.load({"id": "test-id", "cwd": "/tmp"})
    assert session.id == "test-id"
    assert session.cwd == "/tmp"


@pytest.mark.asyncio
async def test_agent_load_invalid_data_raises() -> None:
    """Test AgentCore.load with invalid data raises ValueError."""
    client = MockClient()
    backend = MockBackend()
    tools = MockToolManager()
    agent = AgentCore(client=client, backend=backend, tools=tools)
    with pytest.raises(ValueError, match="Invalid session data"):
        await agent.load("not a dict")


@pytest.mark.asyncio
async def test_agent_load_missing_id_raises() -> None:
    """Test AgentCore.load with missing id raises ValueError."""
    client = MockClient()
    backend = MockBackend()
    tools = MockToolManager()
    agent = AgentCore(client=client, backend=backend, tools=tools)
    with pytest.raises(ValueError, match="Session data missing 'id'"):
        await agent.load({"cwd": "/tmp"})


@pytest.mark.asyncio
async def test_agent_load_with_chain() -> None:
    """Test AgentCore.load restores chain."""
    client = MockClient()
    backend = MockBackend()
    tools = MockToolManager()
    agent = AgentCore(client=client, backend=backend, tools=tools)
    data = {
        "id": "test-id",
        "cwd": "/tmp",
        "chain": [
            {"kind": "user_prompt", "id": "n1", "prompt": "hello"},
            {"kind": "assistant_response", "id": "n2", "text": "hi"},
        ],
    }
    session = await agent.load(data)
    assert session.id == "test-id"
    assert session.tail is not None
    assert session.tail.kind == "assistant_response"
    assert session.tail.text == "hi"
    assert session.tail.prev is not None
    assert session.tail.prev.kind == "user_prompt"
    assert session.tail.prev.prompt == "hello"


@pytest.mark.asyncio
async def test_save_load_round_trip() -> None:
    """Test save and load round-trip."""
    client = MockClient()
    backend = MockBackend(
        [
            BackendTurnResult(output_text="hello", tool_calls=[], finish_reason="completed"),
        ]
    )
    tools = MockToolManager()
    agent = AgentCore(client=client, backend=backend, tools=tools)
    session = await agent.new()
    await session.prompt("hi")
    saved = session.save()

    loaded_session = await agent.load(saved)
    assert loaded_session.id == session.id
    assert loaded_session.cwd == session.cwd
    assert loaded_session.tail is not None
    assert loaded_session.tail.kind == "assistant_response"
    assert loaded_session.tail.text == "hello"
