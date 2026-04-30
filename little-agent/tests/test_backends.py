"""Tests for backend request conversion."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from little_agent.agent.core import AgentCore
from little_agent.agent.nodes import (
    AssistantResponseNode,
    ToolCallNode,
    ToolResultNode,
    UserPromptNode,
)
from little_agent.backends.openai import (
    OpenAIBackend,
    _chain_to_messages,
    _tool_map_to_openai_functions,
)
from little_agent.backends.protocol import BackendTurnResult
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
        "echo": ("Echo", [("text", "string", "text", True)]),
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
    tools = MockToolProvider(tools={"echo": ("Echo", [("text", "string", "text", True)])})
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
    tools = MockToolProvider(tools={"echo": ("Echo", [("text", "string", "text", True)])})
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
    tools = MockToolProvider()
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
    tools = MockToolProvider()
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
async def test_openai_backend_streams_content_chunks() -> None:
    """Test that generate() yields agent_message_chunk updates as tokens arrive."""
    client = MockClient()
    tools = MockToolProvider()
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
    assert len(text_updates) == 3
    assert [u.data["text"] for u in text_updates] == ["Hello", " ", "world"]
