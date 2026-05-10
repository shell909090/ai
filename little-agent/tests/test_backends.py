"""Tests for backend request conversion."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import openai
import pytest

from little_agent.agent.agent import AgentCore
from little_agent.agent.nodes import (
    AssistantResponseNode,
    ToolCallNode,
    ToolResultNode,
    UserPromptNode,
)
from little_agent.backends._base import _StreamAccumulator
from little_agent.backends.exceptions import ContextOverflowError
from little_agent.backends.openai import (
    OpenAIBackend,
    _build_tool_calls,
    _chain_to_messages,
    _format_tool_result,
    _node_to_message,
    _postprocess_orphaned_think,
    _tool_map_to_openai_functions,
)
from little_agent.backends.protocol import BackendTurnResult
from little_agent.tools.manager import ToolManager
from little_agent.tools.protocol import ToolArgDef, ToolDef
from little_agent.types import SessionUpdate
from tests.mocks import MockClient, MockToolProvider


async def _collect(
    gen: AsyncIterator[Any],
) -> tuple[BackendTurnResult, list[SessionUpdate]]:
    """Consume a generate() iterator, returning (result, updates)."""
    updates: list[SessionUpdate] = []
    result: BackendTurnResult | None = None
    async for item in gen:
        if isinstance(item, BackendTurnResult):
            result = item
        else:
            updates.append(item)
    assert result is not None
    return result, updates


class _FakeStream:
    """Minimal fake OpenAI streaming response."""

    def __init__(self, chunks: list[Any]) -> None:
        self._chunks = chunks
        self._pos = 0

    def __aiter__(self) -> "_FakeStream":
        return self

    async def __anext__(self) -> Any:
        if self._pos >= len(self._chunks):
            raise StopAsyncIteration
        chunk = self._chunks[self._pos]
        self._pos += 1
        return chunk


def test_tool_map_to_openai_functions() -> None:
    """Test tool map conversion to OpenAI functions."""
    tool_map = {
        "echo": ToolDef(desc="Echo", args=[ToolArgDef("text", "string", "text", True)]),
    }
    functions = _tool_map_to_openai_functions(tool_map)
    assert len(functions) == 1
    assert functions[0]["function"]["name"] == "echo"
    assert "text" in functions[0]["function"]["parameters"]["properties"]


def test_chain_to_messages() -> None:
    """Test chain to messages conversion."""
    node1 = UserPromptNode(id="1", prev=None, prompt="hello")
    node2 = AssistantResponseNode(id="2", prev=node1, text="hi")
    messages = _chain_to_messages(node2)
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"


def test_chain_to_messages_with_content_block() -> None:
    """Test chain to messages with ContentBlock prompt."""
    node = UserPromptNode(id="1", prev=None, prompt=[{"type": "text", "text": "hello"}])
    messages = _chain_to_messages(node)
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == '[{"type": "text", "text": "hello"}]'


def test_chain_to_messages_with_tool_result() -> None:
    """Test chain to messages with ToolCallNode and ToolResultNode."""
    node1 = UserPromptNode(id="1", prev=None, prompt="hello")
    node2 = ToolCallNode(
        id="2", prev=node1, calls={"c1": {"tool_name": "echo", "arguments": {"text": "hi"}}}
    )
    node3 = ToolResultNode(
        id="3", prev=node2, results={"c1": {"status": "completed", "content": "hi"}}
    )
    messages = _chain_to_messages(node3)
    assert len(messages) == 3
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert messages[2]["role"] == "tool"
    assert messages[2]["content"] == "status: completed\ncontent: hi"


def test_format_tool_result_plain_string() -> None:
    """String values are written as-is without JSON escaping."""
    result = {"status": "completed", "content": "line1\nline2\npath: /foo/bar"}
    text = _format_tool_result(result)
    assert text == "status: completed\ncontent: line1\nline2\npath: /foo/bar"


def test_format_tool_result_non_string_value() -> None:
    """Non-string values fall back to json.dumps."""
    result = {"status": "completed", "content": {"key": "val"}}
    text = _format_tool_result(result)
    assert text == 'status: completed\ncontent: {"key": "val"}'


def test_chain_to_messages_parallel_tool_calls() -> None:
    """Test parallel tool calls merged into single assistant message."""
    node1 = UserPromptNode(id="1", prev=None, prompt="hello")
    node2 = ToolCallNode(
        id="2",
        prev=node1,
        calls={
            "c1": {"tool_name": "echo", "arguments": {"text": "a"}},
            "c2": {"tool_name": "add", "arguments": {"a": 1, "b": 2}},
        },
    )
    messages = _chain_to_messages(node2)
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert len(messages[1]["tool_calls"]) == 2


@pytest.mark.asyncio
async def test_openai_backend_generate() -> None:
    """Test OpenAI backend generate method."""
    client = MockClient()
    tools = ToolManager()
    tools.register(
        MockToolProvider(
            tools={"echo": ToolDef(desc="Echo", args=[ToolArgDef("text", "string", "text", True)])}
        )
    )
    backend = OpenAIBackend(model="gpt-4", api_key="test-key")

    chunk1 = MagicMock()
    chunk1.choices = [MagicMock()]
    chunk1.choices[0].delta.content = "Hello"
    chunk1.choices[0].delta.tool_calls = None
    chunk1.choices[0].delta.reasoning_content = None
    chunk1.choices[0].finish_reason = None
    chunk1.usage = None

    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 10
    mock_usage.completion_tokens = 5
    chunk2 = MagicMock()
    chunk2.choices = [MagicMock()]
    chunk2.choices[0].delta.content = None
    chunk2.choices[0].delta.tool_calls = None
    chunk2.choices[0].delta.reasoning_content = None
    chunk2.choices[0].finish_reason = "stop"
    chunk2.usage = mock_usage

    fake_stream = _FakeStream([chunk1, chunk2])
    backend._client.chat.completions.create = AsyncMock(return_value=fake_stream)  # type: ignore[method-assign]

    agent = AgentCore(client=client, backend=backend, tools=tools)
    session = await agent.new()

    result, updates = await _collect(backend.generate(session))  # type: ignore[arg-type]
    assert result.finish_reason == "completed"
    assert result.output_text == "Hello"
    assert result.usage is not None
    assert result.usage["input_tokens"] == 10
    assert result.usage["output_tokens"] == 5

    text_updates = [u for u in updates if u.type == "agent_message_chunk"]
    assert len(text_updates) == 1
    assert text_updates[0].data["text"] == "Hello"


@pytest.mark.asyncio
async def test_openai_backend_generate_with_tool_calls() -> None:
    """Test OpenAI backend generate with tool calls in response."""
    client = MockClient()
    tools = ToolManager()
    tools.register(
        MockToolProvider(
            tools={"echo": ToolDef(desc="Echo", args=[ToolArgDef("text", "string", "text", True)])}
        )
    )
    backend = OpenAIBackend(model="gpt-4", api_key="test-key")

    tc_delta1 = MagicMock()
    tc_delta1.index = 0
    tc_delta1.id = "c1"
    tc_delta1.function.name = "echo"
    tc_delta1.function.arguments = ""

    chunk1 = MagicMock()
    chunk1.choices = [MagicMock()]
    chunk1.choices[0].delta.content = None
    chunk1.choices[0].delta.tool_calls = [tc_delta1]
    chunk1.choices[0].delta.reasoning_content = None
    chunk1.choices[0].finish_reason = None
    chunk1.usage = None

    tc_delta2 = MagicMock()
    tc_delta2.index = 0
    tc_delta2.id = None
    tc_delta2.function.name = None
    tc_delta2.function.arguments = '{"text": "hello"}'

    chunk2 = MagicMock()
    chunk2.choices = [MagicMock()]
    chunk2.choices[0].delta.content = None
    chunk2.choices[0].delta.tool_calls = [tc_delta2]
    chunk2.choices[0].delta.reasoning_content = None
    chunk2.choices[0].finish_reason = "tool_calls"
    chunk2.usage = None

    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 20
    mock_usage.completion_tokens = 10
    chunk3 = MagicMock()
    chunk3.choices = []
    chunk3.usage = mock_usage

    fake_stream = _FakeStream([chunk1, chunk2, chunk3])
    backend._client.chat.completions.create = AsyncMock(return_value=fake_stream)  # type: ignore[method-assign]

    agent = AgentCore(client=client, backend=backend, tools=tools)
    session = await agent.new()

    result, _ = await _collect(backend.generate(session))  # type: ignore[arg-type]
    assert result.finish_reason == "tool_call"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool_name == "echo"
    assert result.tool_calls[0].arguments == {"text": "hello"}
    assert result.usage is not None
    assert result.usage["input_tokens"] == 20
    assert result.usage["output_tokens"] == 10


def test_openai_backend_base_url() -> None:
    """Test base_url is passed to AsyncOpenAI client."""
    with patch("openai.AsyncOpenAI") as mock_async_openai:
        OpenAIBackend(model="gpt-4", api_key="test-key", base_url="http://localhost:8080/v1")
        mock_async_openai.assert_called_once_with(
            api_key="test-key", base_url="http://localhost:8080/v1"
        )


def test_openai_backend_no_base_url() -> None:
    """Test base_url defaults to None (not passed to AsyncOpenAI)."""
    with patch("openai.AsyncOpenAI") as mock_async_openai:
        OpenAIBackend(model="gpt-4", api_key="test-key")
        mock_async_openai.assert_called_once_with(api_key="test-key")


def test_openai_backend_default_timeout() -> None:
    """Test OpenAIBackend has 60s default timeout."""
    backend = OpenAIBackend(model="gpt-4", api_key="test-key")
    assert backend._timeout == 60.0


def test_openai_backend_custom_timeout() -> None:
    """Test OpenAIBackend stores custom timeout."""
    backend = OpenAIBackend(model="gpt-4", api_key="test-key", timeout=30.0)
    assert backend._timeout == 30.0


@pytest.mark.asyncio
async def test_openai_backend_timeout_raises_backend_timeout_error() -> None:
    """Test that a timed-out API call raises BackendTimeoutError."""
    from little_agent.backends.exceptions import BackendTimeoutError

    client = MockClient()
    tools = ToolManager()
    backend = OpenAIBackend(model="gpt-4", api_key="test-key", timeout=0.001)

    async def slow_create(**_: object) -> None:
        await asyncio.sleep(10)

    backend._client.chat.completions.create = slow_create  # type: ignore[assignment]

    agent = AgentCore(client=client, backend=backend, tools=tools)
    session = await agent.new()

    with pytest.raises(BackendTimeoutError):
        async for _ in backend.generate(session):  # type: ignore[arg-type]
            pass


@pytest.mark.asyncio
async def test_openai_backend_generate_with_reasoning() -> None:
    """Test OpenAI backend extracts reasoning_content into thinking_text."""
    client = MockClient()
    tools = ToolManager()
    backend = OpenAIBackend(model="gpt-4", api_key="test-key")

    chunk1 = MagicMock()
    chunk1.choices = [MagicMock()]
    chunk1.choices[0].delta.content = None
    chunk1.choices[0].delta.tool_calls = None
    chunk1.choices[0].delta.reasoning_content = "I think therefore I am"
    chunk1.choices[0].finish_reason = None
    chunk1.usage = None

    chunk2 = MagicMock()
    chunk2.choices = [MagicMock()]
    chunk2.choices[0].delta.content = "Final answer"
    chunk2.choices[0].delta.tool_calls = None
    chunk2.choices[0].delta.reasoning_content = None
    chunk2.choices[0].finish_reason = "stop"
    chunk2.usage = None

    fake_stream = _FakeStream([chunk1, chunk2])
    backend._client.chat.completions.create = AsyncMock(return_value=fake_stream)  # type: ignore[method-assign]

    agent = AgentCore(client=client, backend=backend, tools=tools)
    session = await agent.new()

    result, updates = await _collect(backend.generate(session))  # type: ignore[arg-type]
    assert result.output_text == "Final answer"
    assert result.thinking_text == "I think therefore I am"

    thinking_updates = [u for u in updates if u.type == "thinking_chunk"]
    assert len(thinking_updates) == 1
    assert thinking_updates[0].data["text"] == "I think therefore I am"


@pytest.mark.asyncio
async def test_openai_backend_generate_with_reasoning_field() -> None:
    """Test delta.reasoning (vendor-specific, e.g. stepfun) is routed to thinking_text."""
    client = MockClient()
    tools = ToolManager()
    backend = OpenAIBackend(model="step-3.6", api_key="test-key")

    chunk1 = MagicMock()
    chunk1.choices = [MagicMock()]
    chunk1.choices[0].delta.content = ""
    chunk1.choices[0].delta.tool_calls = None
    chunk1.choices[0].delta.reasoning_content = None
    chunk1.choices[0].delta.reasoning = "vendor thinking"
    chunk1.choices[0].finish_reason = None
    chunk1.usage = None

    chunk2 = MagicMock()
    chunk2.choices = [MagicMock()]
    chunk2.choices[0].delta.content = "answer"
    chunk2.choices[0].delta.tool_calls = None
    chunk2.choices[0].delta.reasoning_content = None
    chunk2.choices[0].delta.reasoning = None
    chunk2.choices[0].finish_reason = "stop"
    chunk2.usage = None

    backend._client.chat.completions.create = AsyncMock(  # type: ignore[method-assign]
        return_value=_FakeStream([chunk1, chunk2])
    )

    agent = AgentCore(client=client, backend=backend, tools=tools)
    session = await agent.new()

    result, updates = await _collect(backend.generate(session))  # type: ignore[arg-type]
    assert result.thinking_text == "vendor thinking"
    assert result.output_text == "answer"

    thinking_updates = [u for u in updates if u.type == "thinking_chunk"]
    assert len(thinking_updates) == 1
    assert thinking_updates[0].data["text"] == "vendor thinking"


@pytest.mark.asyncio
async def test_openai_backend_streams_content_chunks() -> None:
    """Test that generate() yields agent_message_chunk updates as tokens arrive."""
    client = MockClient()
    tools = ToolManager()
    backend = OpenAIBackend(model="gpt-4", api_key="test-key")

    chunks = []
    for word in ["Hello", " ", "world"]:
        c = MagicMock()
        c.choices = [MagicMock()]
        c.choices[0].delta.content = word
        c.choices[0].delta.tool_calls = None
        c.choices[0].delta.reasoning_content = None
        c.choices[0].finish_reason = None
        c.usage = None
        chunks.append(c)

    final_chunk = MagicMock()
    final_chunk.choices = [MagicMock()]
    final_chunk.choices[0].delta.content = None
    final_chunk.choices[0].delta.tool_calls = None
    final_chunk.choices[0].delta.reasoning_content = None
    final_chunk.choices[0].finish_reason = "stop"
    final_chunk.usage = None
    chunks.append(final_chunk)

    backend._client.chat.completions.create = AsyncMock(return_value=_FakeStream(chunks))  # type: ignore[method-assign]

    agent = AgentCore(client=client, backend=backend, tools=tools)
    session = await agent.new()

    result, updates = await _collect(backend.generate(session))  # type: ignore[arg-type]
    assert result.finish_reason == "completed"
    assert result.output_text == "Hello world"
    text_updates = [u for u in updates if u.type == "agent_message_chunk"]
    # ThinkTagParser holds a lookahead buffer so small chunks may be merged;
    # assert content is correct rather than exact chunk count.
    assert len(text_updates) >= 1
    assert "".join(str(u.data["text"]) for u in text_updates) == "Hello world"


def _make_bad_request_error(message: str, code: str | None = None) -> openai.BadRequestError:
    """Build an openai.BadRequestError with optional `code` attribute."""
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(400, request=request)
    err = openai.BadRequestError(message=message, response=response, body=None)
    if code is not None:
        err.code = code
    return err


def _make_finish_chunk() -> Any:
    """Build a minimal finish-reason chunk that closes the stream."""
    chunk = MagicMock()
    chunk.choices = [MagicMock()]
    chunk.choices[0].delta.content = None
    chunk.choices[0].delta.tool_calls = None
    chunk.choices[0].delta.reasoning_content = None
    chunk.choices[0].finish_reason = "stop"
    chunk.usage = None
    return chunk


def test_openai_backend_default_context_window() -> None:
    """Default context_window is 128000."""
    backend = OpenAIBackend(model="gpt-4", api_key="test-key")
    assert backend.context_window == 128000


def test_openai_backend_custom_context_window() -> None:
    """Custom context_window is exposed as attribute."""
    backend = OpenAIBackend(model="gpt-4", api_key="test-key", context_window=64000)
    assert backend.context_window == 64000


def test_openai_backend_default_max_concurrency() -> None:
    """Default max_concurrency=1 constructs without error."""
    backend = OpenAIBackend(model="gpt-4", api_key="test-key")
    assert backend is not None


@pytest.mark.asyncio
async def test_openai_backend_semaphore_serializes_with_max_concurrency_1() -> None:
    """With max_concurrency=1, two concurrent generate() calls run serially."""
    client = MockClient()
    tools = ToolManager()
    backend = OpenAIBackend(model="gpt-4", api_key="test-key", max_concurrency=1)

    sleep_seconds = 0.05

    async def slow_create(**_: object) -> Any:
        await asyncio.sleep(sleep_seconds)
        return _FakeStream([_make_finish_chunk()])

    backend._client.chat.completions.create = slow_create  # type: ignore[assignment]

    agent = AgentCore(client=client, backend=backend, tools=tools)
    session1 = await agent.new()
    session2 = await agent.new()

    async def run(session: Any) -> float:
        await _collect(backend.generate(session))
        return time.perf_counter()

    start = time.perf_counter()
    end1, end2 = await asyncio.gather(run(session1), run(session2))
    diff = abs(end2 - end1)
    total = max(end1, end2) - start
    assert diff >= 0.04, f"expected serialized completions, diff={diff}"
    assert total >= sleep_seconds * 2 - 0.01


@pytest.mark.asyncio
async def test_openai_backend_semaphore_allows_parallel_with_max_concurrency_2() -> None:
    """With max_concurrency=2, two concurrent generate() calls overlap."""
    client = MockClient()
    tools = ToolManager()
    backend = OpenAIBackend(model="gpt-4", api_key="test-key", max_concurrency=2)

    sleep_seconds = 0.05

    async def slow_create(**_: object) -> Any:
        await asyncio.sleep(sleep_seconds)
        return _FakeStream([_make_finish_chunk()])

    backend._client.chat.completions.create = slow_create  # type: ignore[assignment]

    agent = AgentCore(client=client, backend=backend, tools=tools)
    session1 = await agent.new()
    session2 = await agent.new()

    start = time.perf_counter()
    await asyncio.gather(
        _collect(backend.generate(session1)),
        _collect(backend.generate(session2)),
    )
    elapsed = time.perf_counter() - start
    assert elapsed < sleep_seconds * 1.8, f"expected parallel execution, elapsed={elapsed}"


@pytest.mark.asyncio
async def test_openai_backend_overflow_error_by_code() -> None:
    """BadRequestError with code='context_length_exceeded' maps to ContextOverflowError."""
    client = MockClient()
    tools = ToolManager()
    backend = OpenAIBackend(model="gpt-4", api_key="test-key")

    err = _make_bad_request_error("some msg", code="context_length_exceeded")

    async def raising_create(**_: object) -> Any:
        raise err

    backend._client.chat.completions.create = raising_create  # type: ignore[assignment]

    agent = AgentCore(client=client, backend=backend, tools=tools)
    session = await agent.new()

    with pytest.raises(ContextOverflowError):
        async for _ in backend.generate(session):  # type: ignore[arg-type]
            pass


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    [
        "This model's maximum context length is 4096 tokens.",
        "Input exceeds the context window allowed.",
        "Request rejected: context length too large.",
    ],
)
async def test_openai_backend_overflow_error_by_message_pattern(message: str) -> None:
    """BadRequestError with overflow-pattern message maps to ContextOverflowError."""
    client = MockClient()
    tools = ToolManager()
    backend = OpenAIBackend(model="gpt-4", api_key="test-key")

    err = _make_bad_request_error(message)

    async def raising_create(**_: object) -> Any:
        raise err

    backend._client.chat.completions.create = raising_create  # type: ignore[assignment]

    agent = AgentCore(client=client, backend=backend, tools=tools)
    session = await agent.new()

    with pytest.raises(ContextOverflowError):
        async for _ in backend.generate(session):  # type: ignore[arg-type]
            pass


@pytest.mark.asyncio
async def test_openai_backend_non_overflow_bad_request_reraises() -> None:
    """Non-overflow BadRequestError propagates unchanged."""
    client = MockClient()
    tools = ToolManager()
    backend = OpenAIBackend(model="gpt-4", api_key="test-key")

    err = _make_bad_request_error("invalid api key")

    async def raising_create(**_: object) -> Any:
        raise err

    backend._client.chat.completions.create = raising_create  # type: ignore[assignment]

    agent = AgentCore(client=client, backend=backend, tools=tools)
    session = await agent.new()

    from little_agent.backends.exceptions import BackendError

    with pytest.raises(BackendError):
        async for _ in backend.generate(session):  # type: ignore[arg-type]
            pass


# ---------------------------------------------------------------------------
# T69: _build_tool_calls handles malformed JSON arguments gracefully
# ---------------------------------------------------------------------------


def test_build_tool_calls_bad_json_sets_error_field(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """_build_tool_calls with invalid JSON arguments sets error field and logs at ERROR level."""
    acc: dict[int, dict[str, str]] = {
        0: {"id": "call_abc", "name": "echo", "arguments": "{bad json"},
    }
    with caplog.at_level(logging.ERROR, logger="little_agent.backends.openai"):
        result = _build_tool_calls(acc)

    assert len(result) == 1
    tc = result[0]
    assert tc.call_id == "call_abc"
    assert tc.tool_name == "echo"
    assert tc.arguments == {}
    assert tc.error is not None, "Expected error field to be set on parse failure"

    error_messages = [r.message for r in caplog.records if r.levelno == logging.ERROR]
    assert any("parse" in msg.lower() or "Failed" in msg for msg in error_messages), (
        f"Expected an error log about JSON parsing failure, got: {error_messages}"
    )


def test_build_tool_calls_valid_json_unaffected() -> None:
    """_build_tool_calls with valid JSON arguments parses correctly."""
    acc: dict[int, dict[str, str]] = {
        0: {"id": "call_xyz", "name": "add", "arguments": '{"a": 1, "b": 2}'},
    }
    result = _build_tool_calls(acc)
    assert len(result) == 1
    assert result[0].arguments == {"a": 1, "b": 2}


@pytest.mark.asyncio
async def test_openai_backend_semaphore_releases_on_exception() -> None:
    """Semaphore is released after exception so subsequent generate() works."""
    client = MockClient()
    tools = ToolManager()
    backend = OpenAIBackend(model="gpt-4", api_key="test-key", max_concurrency=1)

    overflow_err = _make_bad_request_error("maximum context length exceeded")
    call_count = {"n": 0}

    async def create_then_succeed(**_: object) -> Any:
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise overflow_err
        return _FakeStream([_make_finish_chunk()])

    backend._client.chat.completions.create = create_then_succeed  # type: ignore[assignment]

    agent = AgentCore(client=client, backend=backend, tools=tools)
    session1 = await agent.new()
    session2 = await agent.new()

    with pytest.raises(ContextOverflowError):
        async for _ in backend.generate(session1):  # type: ignore[arg-type]
            pass

    result, _ = await asyncio.wait_for(_collect(backend.generate(session2)), timeout=1.0)  # type: ignore[arg-type]
    assert result.finish_reason == "completed"


# ---------------------------------------------------------------------------
# ToolCallNode.output_text in OpenAI _node_to_message
# ---------------------------------------------------------------------------


def test_tool_call_node_output_text_in_messages_openai() -> None:
    """OpenAI _node_to_message includes content when output_text is non-empty."""
    n = ToolCallNode(
        id="n1",
        prev=None,
        output_text="I will use bash",
        calls={"c1": {"tool_name": "bash", "arguments": {"cmd": "ls"}}},
    )
    msgs = _node_to_message(n)
    assert len(msgs) == 1
    msg = msgs[0]
    assert msg["role"] == "assistant"
    # content must be set to the output_text
    assert msg.get("content") == "I will use bash"
    # tool_calls must still be present
    assert "tool_calls" in msg
    assert len(msg["tool_calls"]) == 1
    assert msg["tool_calls"][0]["function"]["name"] == "bash"


def test_tool_call_node_empty_output_text_in_messages_openai() -> None:
    """OpenAI _node_to_message omits content key when output_text is empty."""
    n = ToolCallNode(
        id="n2",
        prev=None,
        output_text="",
        calls={"c1": {"tool_name": "echo", "arguments": {"text": "hi"}}},
    )
    msgs = _node_to_message(n)
    assert len(msgs) == 1
    msg = msgs[0]
    assert msg["role"] == "assistant"
    assert "content" not in msg
    assert "tool_calls" in msg


# ---------------------------------------------------------------------------
# _postprocess_orphaned_think
# ---------------------------------------------------------------------------


def test_postprocess_orphaned_think_moves_thinking_before_close_tag() -> None:
    """When </think> present but no reasoning_content, thinking portion is extracted."""
    acc = _StreamAccumulator()
    acc.text = ["I wonder about this.\n", "</think>\n", "Here is my answer."]
    _postprocess_orphaned_think(acc)
    assert "".join(acc.thinking) == "I wonder about this.\n"
    assert "".join(acc.text) == "\nHere is my answer."


def test_postprocess_orphaned_think_no_close_tag_unchanged() -> None:
    """When no </think> in text, accumulator is unchanged."""
    acc = _StreamAccumulator()
    acc.text = ["Plain response without any tags."]
    _postprocess_orphaned_think(acc)
    assert acc.thinking == []
    assert "".join(acc.text) == "Plain response without any tags."


def test_postprocess_orphaned_think_strips_tag_when_thinking_already_set() -> None:
    """When acc.thinking is set (e.g. via delta.reasoning), </think> is stripped from text."""
    acc = _StreamAccumulator()
    acc.thinking = ["Already extracted thinking"]
    acc.text = ["</think>", "actual response"]
    _postprocess_orphaned_think(acc)
    assert acc.thinking == ["Already extracted thinking"]
    assert "".join(acc.text) == "actual response"


def test_postprocess_orphaned_think_strips_tag_with_prefix_when_thinking_set() -> None:
    """Prefix before </think> is discarded when thinking is already set."""
    acc = _StreamAccumulator()
    acc.thinking = ["via delta.reasoning"]
    acc.text = ["junk before tag</think>after tag"]
    _postprocess_orphaned_think(acc)
    assert acc.thinking == ["via delta.reasoning"]
    assert "".join(acc.text) == "after tag"


def test_postprocess_orphaned_think_only_close_tag_no_text_after() -> None:
    """Thinking content with </think> at end and no trailing text."""
    acc = _StreamAccumulator()
    acc.text = ["thinking only</think>"]
    _postprocess_orphaned_think(acc)
    assert "".join(acc.thinking) == "thinking only"
    assert acc.text == []


@pytest.mark.asyncio
async def test_openai_backend_orphaned_close_tag_extracted_as_thinking() -> None:
    """When LiteLLM strips <think> but leaves </think> in delta.content, thinking is correct."""
    client = MockClient()
    tools = ToolManager()
    backend = OpenAIBackend(model="gpt-4", api_key="test-key")

    # Simulate LiteLLM stripping <think>: thinking content comes in delta.content
    # without the opening tag, but </think> is present at the end.
    chunks = []
    for text in ["thinking content", "</think>", "visible answer"]:
        c = MagicMock()
        c.choices = [MagicMock()]
        c.choices[0].delta.content = text
        c.choices[0].delta.tool_calls = None
        c.choices[0].delta.reasoning_content = None
        c.choices[0].delta.reasoning = None
        c.choices[0].finish_reason = None
        c.usage = None
        chunks.append(c)

    final = MagicMock()
    final.choices = [MagicMock()]
    final.choices[0].delta.content = None
    final.choices[0].delta.tool_calls = None
    final.choices[0].delta.reasoning_content = None
    final.choices[0].delta.reasoning = None
    final.choices[0].finish_reason = "stop"
    final.usage = None
    chunks.append(final)

    backend._client.chat.completions.create = AsyncMock(return_value=_FakeStream(chunks))  # type: ignore[method-assign]

    agent = AgentCore(client=client, backend=backend, tools=tools)
    session = await agent.new()

    result, _ = await _collect(backend.generate(session))  # type: ignore[arg-type]
    assert result.thinking_text == "thinking content"
    assert result.output_text == "visible answer"


@pytest.mark.asyncio
async def test_openai_backend_reasoning_field_with_orphaned_close_tag() -> None:
    """Stepfun pattern: delta.reasoning carries thinking; delta.content carries </think>."""
    client = MockClient()
    tools = ToolManager()
    backend = OpenAIBackend(model="step-3.6", api_key="test-key")

    # Chunk 1: thinking via delta.reasoning, content empty
    c1 = MagicMock()
    c1.choices = [MagicMock()]
    c1.choices[0].delta.content = ""
    c1.choices[0].delta.tool_calls = None
    c1.choices[0].delta.reasoning_content = None
    c1.choices[0].delta.reasoning = "I am thinking"
    c1.choices[0].finish_reason = None
    c1.usage = None

    # Chunk 2: end-of-thinking signal as </think> in content
    c2 = MagicMock()
    c2.choices = [MagicMock()]
    c2.choices[0].delta.content = "</think>"
    c2.choices[0].delta.tool_calls = None
    c2.choices[0].delta.reasoning_content = None
    c2.choices[0].delta.reasoning = None
    c2.choices[0].finish_reason = None
    c2.usage = None

    # Chunk 3: actual response
    c3 = MagicMock()
    c3.choices = [MagicMock()]
    c3.choices[0].delta.content = "Here is my answer"
    c3.choices[0].delta.tool_calls = None
    c3.choices[0].delta.reasoning_content = None
    c3.choices[0].delta.reasoning = None
    c3.choices[0].finish_reason = "stop"
    c3.usage = None

    backend._client.chat.completions.create = AsyncMock(  # type: ignore[method-assign]
        return_value=_FakeStream([c1, c2, c3])
    )

    agent = AgentCore(client=client, backend=backend, tools=tools)
    session = await agent.new()

    result, _ = await _collect(backend.generate(session))  # type: ignore[arg-type]
    assert result.thinking_text == "I am thinking"
    assert result.output_text == "Here is my answer"
