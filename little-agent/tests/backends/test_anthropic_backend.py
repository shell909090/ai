"""Tests for AnthropicBackend request conversion and streaming.

The actual implementation in little_agent/backends/anthropic.py:
- _chain_to_messages(session) walks session.tail (a SessionCore), not a raw Node
- _open_stream calls self._client.messages.stream(**kwargs).__aenter__() via asyncio.wait_for
- The returned stream object is iterated via stream.event_stream
- stream.__aexit__() is called in a finally block
"""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from little_agent.agent.agent import AgentCore
from little_agent.agent.nodes import (
    AssistantResponseNode,
    SummaryNode,
    ToolCallNode,
    ToolResultNode,
    UserPromptNode,
)
from little_agent.agent.session import SessionCore
from little_agent.backends.exceptions import BackendError, ContextOverflowError
from little_agent.backends.protocol import BackendTurnResult
from little_agent.tools.manager import ToolManager
from little_agent.tools.protocol import ToolArgDef, ToolDef
from little_agent.types import SessionUpdate
from tests.mocks import MockClient

_ANTHROPIC_BACKEND_MODULE = "little_agent.backends.anthropic"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _make_session_with_tail(tail_node: Any) -> MagicMock:
    """Make a minimal SessionCore-like mock with a given tail node and empty tool map."""
    session = MagicMock(spec=SessionCore)
    session.tail = tail_node
    session.get_turn_tool_map.return_value = {}
    return session


# ---------------------------------------------------------------------------
# Fake streaming infrastructure
#
# The real AnthropicBackend does:
#   stream = await asyncio.wait_for(
#       self._client.messages.stream(**kwargs).__aenter__(), timeout=...
#   )
#   async for event in stream.event_stream: ...
#   await stream.__aexit__(None, None, None)
#
# So: messages.stream(**kwargs) must return something whose __aenter__ is awaitable
# and the result must have .event_stream as an async iterable.
# ---------------------------------------------------------------------------


class _FakeEventStream:
    """Async iterable of fake events used as stream.event_stream."""

    def __init__(self, events: list[Any]) -> None:
        self._events = events
        self._pos = 0

    def __aiter__(self) -> "_FakeEventStream":
        self._pos = 0
        return self

    async def __anext__(self) -> Any:
        if self._pos >= len(self._events):
            raise StopAsyncIteration
        event = self._events[self._pos]
        self._pos += 1
        return event


class _FakeStream:
    """Fake opened stream supporting async-for iteration directly."""

    def __init__(self, events: list[Any]) -> None:
        self._iter = _FakeEventStream(events)

    def __aiter__(self) -> "_FakeEventStream":
        return self._iter

    async def __aexit__(self, *args: Any) -> None:
        pass


class _FakeStreamCM:
    """Fake context manager returned by messages.stream(); __aenter__ returns _FakeStream."""

    def __init__(self, events: list[Any]) -> None:
        self._stream = _FakeStream(events)

    async def __aenter__(self) -> _FakeStream:
        return self._stream

    async def __aexit__(self, *args: Any) -> None:
        pass


# ---------------------------------------------------------------------------
# Event factories
# ---------------------------------------------------------------------------


def _make_text_delta_event(text: str, index: int = 0) -> MagicMock:
    event = MagicMock()
    event.type = "content_block_delta"
    event.index = index
    event.delta = MagicMock()
    event.delta.type = "text_delta"
    event.delta.text = text
    return event


def _make_thinking_delta_event(text: str, index: int = 0) -> MagicMock:
    event = MagicMock()
    event.type = "content_block_delta"
    event.index = index
    event.delta = MagicMock()
    event.delta.type = "thinking_delta"
    event.delta.thinking = text
    return event


def _make_input_json_delta_event(partial_json: str, index: int) -> MagicMock:
    event = MagicMock()
    event.type = "content_block_delta"
    event.index = index
    event.delta = MagicMock()
    event.delta.type = "input_json_delta"
    event.delta.partial_json = partial_json
    return event


def _make_content_block_start_tool_use(call_id: str, name: str, index: int) -> MagicMock:
    event = MagicMock()
    event.type = "content_block_start"
    event.index = index
    event.content_block = MagicMock()
    event.content_block.type = "tool_use"
    event.content_block.id = call_id
    event.content_block.name = name
    return event


def _make_message_delta_event(
    stop_reason: str = "end_turn",
    output_tokens: int = 5,
) -> MagicMock:
    event = MagicMock()
    event.type = "message_delta"
    event.delta = MagicMock()
    event.delta.stop_reason = stop_reason
    event.usage = MagicMock()
    event.usage.input_tokens = None
    event.usage.output_tokens = output_tokens
    event.usage.cache_read_input_tokens = None
    return event


def _make_message_start_event(input_tokens: int = 10) -> MagicMock:
    event = MagicMock()
    event.type = "message_start"
    event.message = MagicMock()
    event.message.usage = MagicMock()
    event.message.usage.input_tokens = input_tokens
    event.message.usage.output_tokens = 0
    event.message.usage.cache_read_input_tokens = None
    return event


def _make_unrelated_event() -> MagicMock:
    event = MagicMock()
    event.type = "content_block_stop"
    return event


# ---------------------------------------------------------------------------
# Exception stand-in
# ---------------------------------------------------------------------------


class _FakeAPIError(Exception):
    """Stand-in for anthropic.APIError (base of all SDK errors)."""


class _FakeBadRequestError(_FakeAPIError):
    """Stand-in for anthropic.BadRequestError."""

    def __init__(self, message: str = "") -> None:
        super().__init__(message)
        self.message = message


class _FakeRateLimitError(_FakeAPIError):
    """Stand-in for anthropic.RateLimitError."""


# ---------------------------------------------------------------------------
# Backend factory helpers
# ---------------------------------------------------------------------------


def _make_backend(
    mod: Any,
    system: str | None = None,
    context_window: int = 128000,
    max_concurrency: int = 1,
) -> tuple[Any, MagicMock]:
    """Return (backend, mock_api_client) with anthropic module mocked out."""
    mock_api_client = MagicMock()
    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic = MagicMock(return_value=mock_api_client)
    mock_anthropic.BadRequestError = _FakeBadRequestError
    mock_anthropic.RateLimitError = _FakeRateLimitError
    mock_anthropic.APIError = _FakeAPIError

    kwargs: dict[str, Any] = {
        "model": "claude-3-5-sonnet-latest",
        "api_key": "test-key",
        "context_window": context_window,
        "max_concurrency": max_concurrency,
    }
    if system is not None:
        kwargs["system"] = system

    with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
        backend = mod.AnthropicBackend(**kwargs)

    return backend, mock_api_client


async def _run_backend_with_events(
    backend: Any,
    events: list[Any],
) -> tuple[BackendTurnResult, list[SessionUpdate]]:
    """Wire a fake stream and run the backend through a fresh session.

    The backend's _open_stream does 'import anthropic' at call time, so we must
    keep sys.modules patched during the entire generate() call.
    """
    backend._client.messages.stream = MagicMock(return_value=_FakeStreamCM(events))

    tools = ToolManager()
    client_mock = MockClient()
    agent = AgentCore(client=client_mock, backend=backend, tools=tools)
    session = await agent.new()

    mock_anthropic = MagicMock()
    mock_anthropic.BadRequestError = _FakeBadRequestError
    with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
        return await _collect(backend.generate(session))


# ---------------------------------------------------------------------------
# Tests: _tool_map_to_anthropic_tools
# ---------------------------------------------------------------------------


class TestToolMapToAnthropicTools:
    """Tests for _tool_map_to_anthropic_tools."""

    def test_single_tool_with_required_arg(self) -> None:
        mod = pytest.importorskip(_ANTHROPIC_BACKEND_MODULE)
        tool_map = {
            "echo": ToolDef(
                desc="Echo text",
                args=[ToolArgDef("text", "string", "text to echo", True)],
            )
        }
        tools = mod._tool_map_to_anthropic_tools(tool_map)
        assert len(tools) == 1
        t = tools[0]
        assert t["name"] == "echo"
        assert t["description"] == "Echo text"
        schema = t["input_schema"]
        assert schema["type"] == "object"
        assert "text" in schema["properties"]
        assert schema["properties"]["text"]["type"] == "string"
        assert "text" in schema["required"]

    def test_optional_arg_not_in_required(self) -> None:
        mod = pytest.importorskip(_ANTHROPIC_BACKEND_MODULE)
        tool_map = {
            "greet": ToolDef(
                desc="Greet",
                args=[
                    ToolArgDef("name", "string", "name", True),
                    ToolArgDef("title", "string", "title", False),
                ],
            )
        }
        tools = mod._tool_map_to_anthropic_tools(tool_map)
        schema = tools[0]["input_schema"]
        assert "name" in schema["required"]
        assert "title" not in schema["required"]

    def test_multiple_tools(self) -> None:
        mod = pytest.importorskip(_ANTHROPIC_BACKEND_MODULE)
        tool_map = {
            "a": ToolDef(desc="A", args=[]),
            "b": ToolDef(desc="B", args=[]),
        }
        tools = mod._tool_map_to_anthropic_tools(tool_map)
        assert len(tools) == 2
        names = {t["name"] for t in tools}
        assert names == {"a", "b"}

    def test_no_args_produces_empty_properties(self) -> None:
        mod = pytest.importorskip(_ANTHROPIC_BACKEND_MODULE)
        tool_map = {"noop": ToolDef(desc="no-op", args=[])}
        tools = mod._tool_map_to_anthropic_tools(tool_map)
        schema = tools[0]["input_schema"]
        assert schema["properties"] == {}
        assert schema["required"] == []


# ---------------------------------------------------------------------------
# Tests: _chain_to_messages — uses session.tail walk
# ---------------------------------------------------------------------------


class TestChainToMessages:
    """Tests for _chain_to_messages covering each node type."""

    def test_user_prompt_node(self) -> None:
        mod = pytest.importorskip(_ANTHROPIC_BACKEND_MODULE)
        node = UserPromptNode(id="1", prev=None, prompt="hello world")
        session = _make_session_with_tail(node)
        msgs, _ = mod._chain_to_messages(session)
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "hello world"

    def test_assistant_response_node(self) -> None:
        mod = pytest.importorskip(_ANTHROPIC_BACKEND_MODULE)
        n1 = UserPromptNode(id="1", prev=None, prompt="hi")
        n2 = AssistantResponseNode(id="2", prev=n1, text="hello back")
        session = _make_session_with_tail(n2)
        msgs, _ = mod._chain_to_messages(session)
        assert len(msgs) == 2
        assert msgs[1]["role"] == "assistant"
        content = msgs[1]["content"]
        assert isinstance(content, list)
        assert content[0]["type"] == "text"
        assert content[0]["text"] == "hello back"

    def test_tool_call_node(self) -> None:
        mod = pytest.importorskip(_ANTHROPIC_BACKEND_MODULE)
        n1 = UserPromptNode(id="1", prev=None, prompt="go")
        n2 = ToolCallNode(
            id="2",
            prev=n1,
            calls={"c1": {"tool_name": "bash", "arguments": {"cmd": "ls"}}},
        )
        session = _make_session_with_tail(n2)
        msgs, _ = mod._chain_to_messages(session)
        assert len(msgs) == 2
        assistant_msg = msgs[1]
        assert assistant_msg["role"] == "assistant"
        content = assistant_msg["content"]
        assert isinstance(content, list)
        block = content[0]
        assert block["type"] == "tool_use"
        assert block["id"] == "c1"
        assert block["name"] == "bash"
        assert block["input"] == {"cmd": "ls"}

    def test_tool_call_node_with_output_text(self) -> None:
        """ToolCallNode with output_text produces text block before tool_use block."""
        mod = pytest.importorskip(_ANTHROPIC_BACKEND_MODULE)
        n1 = UserPromptNode(id="1", prev=None, prompt="go")
        n2 = ToolCallNode(
            id="2",
            prev=n1,
            output_text="I will use bash",
            calls={"c1": {"tool_name": "bash", "arguments": {"cmd": "ls"}}},
        )
        session = _make_session_with_tail(n2)
        msgs, _ = mod._chain_to_messages(session)
        assert len(msgs) == 2
        assistant_msg = msgs[1]
        assert assistant_msg["role"] == "assistant"
        content = assistant_msg["content"]
        assert isinstance(content, list)
        # First block must be the text block for output_text
        assert content[0]["type"] == "text"
        assert content[0]["text"] == "I will use bash"
        # Second block must be the tool_use block
        assert content[1]["type"] == "tool_use"
        assert content[1]["id"] == "c1"
        assert content[1]["name"] == "bash"

    def test_tool_call_node_empty_output_text(self) -> None:
        """ToolCallNode with empty output_text produces only tool_use block."""
        mod = pytest.importorskip(_ANTHROPIC_BACKEND_MODULE)
        n1 = UserPromptNode(id="1", prev=None, prompt="go")
        n2 = ToolCallNode(
            id="2",
            prev=n1,
            output_text="",
            calls={"c1": {"tool_name": "bash", "arguments": {"cmd": "ls"}}},
        )
        session = _make_session_with_tail(n2)
        msgs, _ = mod._chain_to_messages(session)
        assert len(msgs) == 2
        content = msgs[1]["content"]
        assert isinstance(content, list)
        # Only one block: the tool_use block, no text block
        assert len(content) == 1
        assert content[0]["type"] == "tool_use"

    def test_tool_result_node(self) -> None:
        mod = pytest.importorskip(_ANTHROPIC_BACKEND_MODULE)
        n1 = UserPromptNode(id="1", prev=None, prompt="go")
        n2 = ToolCallNode(
            id="2",
            prev=n1,
            calls={"c1": {"tool_name": "bash", "arguments": {}}},
        )
        n3 = ToolResultNode(
            id="3",
            prev=n2,
            results={"c1": {"status": "completed", "content": "output text"}},
        )
        session = _make_session_with_tail(n3)
        msgs, _ = mod._chain_to_messages(session)
        assert len(msgs) == 3
        result_msg = msgs[2]
        assert result_msg["role"] == "user"
        content = result_msg["content"]
        assert isinstance(content, list)
        block = content[0]
        assert block["type"] == "tool_result"
        assert block["tool_use_id"] == "c1"
        assert "output text" in block["content"]

    def test_summary_node(self) -> None:
        mod = pytest.importorskip(_ANTHROPIC_BACKEND_MODULE)
        n1 = SummaryNode(id="1", prev=None, summary="summary text")
        session = _make_session_with_tail(n1)
        msgs, system_injected = mod._chain_to_messages(session)
        # First SummaryNode is lifted to system_injected, not kept in messages.
        assert len(msgs) == 0
        assert system_injected == "summary text"

    def test_parallel_tool_calls(self) -> None:
        mod = pytest.importorskip(_ANTHROPIC_BACKEND_MODULE)
        n1 = UserPromptNode(id="1", prev=None, prompt="do stuff")
        n2 = ToolCallNode(
            id="2",
            prev=n1,
            calls={
                "c1": {"tool_name": "echo", "arguments": {"text": "a"}},
                "c2": {"tool_name": "add", "arguments": {"a": 1, "b": 2}},
            },
        )
        session = _make_session_with_tail(n2)
        msgs, _ = mod._chain_to_messages(session)
        assert len(msgs) == 2
        assistant_msg = msgs[1]
        assert assistant_msg["role"] == "assistant"
        content = assistant_msg["content"]
        assert isinstance(content, list)
        assert len(content) == 2
        ids = {block["id"] for block in content}
        assert ids == {"c1", "c2"}


# ---------------------------------------------------------------------------
# Tests: _format_tool_result (now in _utils)
# ---------------------------------------------------------------------------


class TestFormatToolResultContent:
    """Tests for _format_tool_result via _utils."""

    def test_string_passthrough(self) -> None:
        from little_agent.backends._utils import _format_tool_result

        result = {"status": "completed", "content": "some text"}
        text = _format_tool_result(result)
        assert "some text" in text

    def test_non_string_json_dumps(self) -> None:
        from little_agent.backends._utils import _format_tool_result

        result = {"status": "completed", "content": {"key": "value"}}
        text = _format_tool_result(result)
        assert '"key"' in text
        assert '"value"' in text


# ---------------------------------------------------------------------------
# Tests: AnthropicBackend.__init__
# ---------------------------------------------------------------------------


class TestAnthropicBackendInit:
    """Tests for AnthropicBackend construction."""

    def test_default_context_window(self) -> None:
        mod = pytest.importorskip(_ANTHROPIC_BACKEND_MODULE)
        backend, _ = _make_backend(mod)
        assert backend.context_window == 128000

    def test_custom_context_window(self) -> None:
        mod = pytest.importorskip(_ANTHROPIC_BACKEND_MODULE)
        backend, _ = _make_backend(mod, context_window=64000)
        assert backend.context_window == 64000

    def test_default_max_concurrency_constructs(self) -> None:
        mod = pytest.importorskip(_ANTHROPIC_BACKEND_MODULE)
        backend, _ = _make_backend(mod)
        assert backend is not None


# ---------------------------------------------------------------------------
# Tests: AnthropicBackend.generate — streaming text
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_anthropic_backend_generate_text() -> None:
    """Streaming text events produce agent_message_chunk updates and BackendTurnResult."""
    mod = pytest.importorskip(_ANTHROPIC_BACKEND_MODULE)
    backend, _ = _make_backend(mod)

    events = [
        _make_message_start_event(input_tokens=10),
        _make_text_delta_event("Hello"),
        _make_text_delta_event(", world"),
        _make_message_delta_event(stop_reason="end_turn", output_tokens=5),
        _make_unrelated_event(),
    ]

    result, updates = await _run_backend_with_events(backend, events)
    assert result.finish_reason == "completed"
    assert result.output_text == "Hello, world"
    assert result.usage is not None
    assert result.usage.get("input_tokens") == 10
    assert result.usage.get("output_tokens") == 5

    text_updates = [u for u in updates if u.type == "agent_message_chunk"]
    combined = "".join(u.data["text"] for u in text_updates)
    assert combined == "Hello, world"


@pytest.mark.asyncio
async def test_anthropic_backend_generate_tool_call() -> None:
    """tool_use stop_reason produces tool_call BackendTurnResult with BackendToolCall."""
    mod = pytest.importorskip(_ANTHROPIC_BACKEND_MODULE)
    backend, _ = _make_backend(mod)

    events = [
        _make_message_start_event(input_tokens=20),
        _make_content_block_start_tool_use("call-1", "echo", index=0),
        _make_input_json_delta_event('{"text": "hi"}', index=0),
        _make_message_delta_event(stop_reason="tool_use", output_tokens=8),
    ]

    result, _ = await _run_backend_with_events(backend, events)
    assert result.finish_reason == "tool_call"
    assert len(result.tool_calls) == 1
    tc = result.tool_calls[0]
    assert tc.call_id == "call-1"
    assert tc.tool_name == "echo"
    assert tc.arguments == {"text": "hi"}


@pytest.mark.asyncio
async def test_anthropic_backend_generate_thinking() -> None:
    """thinking_delta events produce thinking_chunk updates and populate thinking_text."""
    mod = pytest.importorskip(_ANTHROPIC_BACKEND_MODULE)
    backend, _ = _make_backend(mod)

    events = [
        _make_message_start_event(input_tokens=10),
        _make_thinking_delta_event("I think therefore I am"),
        _make_text_delta_event("42"),
        _make_message_delta_event(stop_reason="end_turn", output_tokens=5),
    ]

    result, updates = await _run_backend_with_events(backend, events)
    assert result.output_text == "42"
    assert result.thinking_text == "I think therefore I am"

    thinking_updates = [u for u in updates if u.type == "thinking_chunk"]
    combined = "".join(u.data["text"] for u in thinking_updates)
    assert combined == "I think therefore I am"


@pytest.mark.asyncio
async def test_anthropic_backend_max_tokens_equals_context_window() -> None:
    """max_tokens passed to the API equals context_window."""
    mod = pytest.importorskip(_ANTHROPIC_BACKEND_MODULE)
    backend, _ = _make_backend(mod, context_window=32000)

    captured: dict[str, Any] = {}

    def _capture(**kwargs: Any) -> _FakeStreamCM:
        captured.update(kwargs)
        return _FakeStreamCM(
            [
                _make_message_start_event(),
                _make_message_delta_event(stop_reason="end_turn"),
            ]
        )

    backend._client.messages.stream = _capture

    mock_anthropic = MagicMock()
    mock_anthropic.BadRequestError = _FakeBadRequestError
    tools = ToolManager()
    client_mock = MockClient()
    agent = AgentCore(client=client_mock, backend=backend, tools=tools)
    session = await agent.new()
    with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
        await _collect(backend.generate(session))

    # max_tokens must NOT equal context_window (P1-5 fix); default is 8192
    assert captured.get("max_tokens") == 8192
    assert captured.get("max_tokens") != captured.get("context_window", 128000)


@pytest.mark.asyncio
async def test_anthropic_backend_system_prompt_passed() -> None:
    """System prompt is forwarded to the API as 'system' kwarg."""
    mod = pytest.importorskip(_ANTHROPIC_BACKEND_MODULE)
    backend, _ = _make_backend(mod, system="You are a helpful assistant.")

    captured: dict[str, Any] = {}

    def _capture(**kwargs: Any) -> _FakeStreamCM:
        captured.update(kwargs)
        return _FakeStreamCM(
            [
                _make_message_start_event(),
                _make_message_delta_event(stop_reason="end_turn"),
            ]
        )

    backend._client.messages.stream = _capture

    mock_anthropic = MagicMock()
    mock_anthropic.BadRequestError = _FakeBadRequestError
    tools = ToolManager()
    client_mock = MockClient()
    agent = AgentCore(client=client_mock, backend=backend, tools=tools)
    session = await agent.new()
    with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
        await _collect(backend.generate(session))

    assert captured.get("system") == "You are a helpful assistant."


# ---------------------------------------------------------------------------
# Tests: context overflow detection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    [
        "prompt is too long for this model",
        "request contains too many tokens",
        "exceeded maximum context length",
    ],
)
async def test_anthropic_backend_overflow_error_by_message(message: str) -> None:
    """BadRequestError with overflow-pattern message maps to ContextOverflowError."""
    mod = pytest.importorskip(_ANTHROPIC_BACKEND_MODULE)
    backend, _ = _make_backend(mod)

    err = _FakeBadRequestError(message)

    def _raise(**_: Any) -> Any:
        raise err

    backend._client.messages.stream = _raise

    mock_anthropic = MagicMock()
    mock_anthropic.BadRequestError = _FakeBadRequestError
    mock_anthropic.RateLimitError = _FakeRateLimitError
    mock_anthropic.APIError = _FakeAPIError
    with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
        tools = ToolManager()
        client_mock = MockClient()
        agent = AgentCore(client=client_mock, backend=backend, tools=tools)
        session = await agent.new()

        with pytest.raises(ContextOverflowError):
            async for _ in backend.generate(session):
                pass


@pytest.mark.asyncio
async def test_anthropic_backend_non_overflow_bad_request_reraises() -> None:
    """Non-overflow BadRequestError propagates unchanged."""
    mod = pytest.importorskip(_ANTHROPIC_BACKEND_MODULE)
    backend, _ = _make_backend(mod)

    err = _FakeBadRequestError("invalid api key format")

    def _raise(**_: Any) -> Any:
        raise err

    backend._client.messages.stream = _raise

    mock_anthropic = MagicMock()
    mock_anthropic.BadRequestError = _FakeBadRequestError
    mock_anthropic.RateLimitError = _FakeRateLimitError
    mock_anthropic.APIError = _FakeAPIError
    with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
        tools = ToolManager()
        client_mock = MockClient()
        agent = AgentCore(client=client_mock, backend=backend, tools=tools)
        session = await agent.new()

        with pytest.raises(BackendError):
            async for _ in backend.generate(session):
                pass
