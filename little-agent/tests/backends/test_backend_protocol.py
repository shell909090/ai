"""Tests for BackendTurnResult and BackendToolCall data classes."""

from __future__ import annotations

from little_agent.backends.protocol import BackendToolCall, BackendTurnResult


def test_backend_turn_result_completed() -> None:
    """BackendTurnResult with finish_reason='completed' is valid."""
    result = BackendTurnResult(
        output_text="hello",
        tool_calls=[],
        finish_reason="completed",
    )
    assert result.output_text == "hello"
    assert result.finish_reason == "completed"
    assert result.tool_calls == []
    assert result.usage is None
    assert result.thinking_text is None


def test_backend_turn_result_tool_call() -> None:
    """BackendTurnResult with finish_reason='tool_call' includes tool calls."""
    tc = BackendToolCall(call_id="c1", tool_name="bash", arguments={"command": "ls"})
    result = BackendTurnResult(
        output_text="",
        tool_calls=[tc],
        finish_reason="tool_call",
    )
    assert result.finish_reason == "tool_call"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].call_id == "c1"
    assert result.tool_calls[0].tool_name == "bash"


def test_backend_tool_call_error_field() -> None:
    """BackendToolCall has an optional error field."""
    tc = BackendToolCall(call_id="c1", tool_name="echo", arguments={}, error="bad json")
    assert tc.error == "bad json"


def test_backend_turn_result_with_usage() -> None:
    """BackendTurnResult accepts usage dict."""
    result = BackendTurnResult(
        output_text="hi",
        tool_calls=[],
        finish_reason="completed",
        usage={"input_tokens": 10, "output_tokens": 5},
    )
    assert result.usage is not None
    assert result.usage["input_tokens"] == 10


def test_backend_turn_result_with_thinking() -> None:
    """BackendTurnResult accepts thinking_text."""
    result = BackendTurnResult(
        output_text="answer",
        tool_calls=[],
        finish_reason="completed",
        thinking_text="let me think",
    )
    assert result.thinking_text == "let me think"


def test_is_context_overflow() -> None:
    """_is_context_overflow matches by code and message patterns."""
    from little_agent.backends._utils import _is_context_overflow

    class _FakeRuntimeError(Exception):
        """Stand-in for generic SDK error."""

    # Match by substring
    err = _FakeRuntimeError("prompt is too long for the model")
    assert _is_context_overflow(err, ("prompt is too long",))

    # Match by code attribute
    err2 = _FakeRuntimeError("some message")
    err2.code = "context_length_exceeded"  # type: ignore[attr-defined]
    assert _is_context_overflow(err2, (), code="context_length_exceeded")

    # No match
    err3 = _FakeRuntimeError("invalid api key")
    assert not _is_context_overflow(err3, ("prompt is too long",))
