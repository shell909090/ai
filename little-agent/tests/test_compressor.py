"""Tests for LLMCompressor."""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

from little_agent.agent.compressor import (
    LLMCompressor,
    _CompressorSession,
    _nodes_to_text,
    _split_into_turns,
)
from little_agent.agent.nodes import (
    AssistantNode,
    Node,
    ToolResultNode,
    UserPromptNode,
)
from little_agent.backends.protocol import BackendTurnResult
from tests.mocks import MockBackend

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_turn(
    messages: list[Node],
    turn_id: str,
    prompt: str = "user msg",
    reply: str = "assistant reply",
) -> None:
    """Append a (UserPromptNode, AssistantNode) turn to messages in place."""
    u = UserPromptNode(id=f"{turn_id}-u", prompt=prompt)
    a = AssistantNode(id=f"{turn_id}-a", text=reply)
    messages.extend([u, a])


def _count_turns(nodes: list[Node]) -> int:
    """Count the number of UserPromptNodes in a list (= number of turns)."""
    return sum(1 for n in nodes if isinstance(n, UserPromptNode))


# ---------------------------------------------------------------------------
# 1. compress([]) skips when not enough turns
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compress_skips_when_not_enough_turns() -> None:
    """Compress returns no-op when total turns <= keep_turns."""
    backend = MockBackend()
    compressor = LLMCompressor(backend, keep_turns=3)
    messages: list[Node] = []
    _make_turn(messages, "1")
    _make_turn(messages, "2")
    # Only 2 turns, keep_turns=3 → no compression
    summary, remaining = await compressor.compress(messages)
    assert summary == ""
    assert remaining is messages
    # backend was never called
    assert backend._index == 0


@pytest.mark.asyncio
async def test_compress_skips_when_exact_k_turns() -> None:
    """With exactly K turns in the list, compress returns the original list unchanged."""
    backend = MockBackend()
    compressor = LLMCompressor(backend, keep_turns=3)
    messages: list[Node] = []
    _make_turn(messages, "t1")
    _make_turn(messages, "t2")
    _make_turn(messages, "t3")

    summary, remaining = await compressor.compress(messages)
    assert summary == ""
    assert remaining is messages
    assert backend._index == 0


# ---------------------------------------------------------------------------
# 2. compress returns summary and preserve zone
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compress_returns_summary_and_preserve_zone() -> None:
    """Compress summarizes old turns and returns (summary_text, preserve_zone)."""
    backend = MockBackend(
        [
            BackendTurnResult(
                output_text="compressed-turn-1", tool_calls=[], finish_reason="completed"
            )
        ]
    )
    compressor = LLMCompressor(backend, keep_turns=2)
    messages: list[Node] = []
    _make_turn(messages, "1", reply="reply 1")
    _make_turn(messages, "2", reply="reply 2")
    _make_turn(messages, "3", reply="reply 3")
    # 3 turns, keep_turns=2 → turn 1 compressed, turns 2 & 3 preserved
    summary, remaining = await compressor.compress(messages)
    assert summary != ""
    assert _count_turns(remaining) == 2


# ---------------------------------------------------------------------------
# 3. Exactly K turns preserved after compression
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compress_preserves_k_turns() -> None:
    """After compression the preserved zone contains exactly keep_turns UserPromptNodes."""
    k = 3
    total_turns = 6
    backend = MockBackend(
        [
            BackendTurnResult(output_text=f"sum{i}", tool_calls=[], finish_reason="completed")
            for i in range(total_turns - k)
        ]
    )
    compressor = LLMCompressor(backend, keep_turns=k)

    messages: list[Node] = []
    for i in range(total_turns):
        _make_turn(messages, f"t{i}")

    summary, remaining = await compressor.compress(messages)
    assert summary != ""
    assert _count_turns(remaining) == k


# ---------------------------------------------------------------------------
# 4. Multiple turns compressed into one summary string (joined with "\n\n")
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compress_multiple_turns_joined_in_summary() -> None:
    r"""Summaries from multiple compressed turns are joined with '\n\n'."""
    backend = MockBackend(
        [
            BackendTurnResult(output_text="part-1", tool_calls=[], finish_reason="completed"),
            BackendTurnResult(output_text="part-2", tool_calls=[], finish_reason="completed"),
        ]
    )
    compressor = LLMCompressor(backend, keep_turns=1)
    messages: list[Node] = []
    _make_turn(messages, "1")
    _make_turn(messages, "2")
    _make_turn(messages, "3")
    # 3 turns, keep=1 → 2 compressed
    summary, remaining = await compressor.compress(messages)
    assert "part-1" in summary
    assert "part-2" in summary
    assert "\n\n" in summary


# ---------------------------------------------------------------------------
# 5. _split_into_turns correctness
# ---------------------------------------------------------------------------


def test_compress_splits_turns_correctly() -> None:
    """_split_into_turns groups nodes so each turn starts with a UserPromptNode."""
    u1 = UserPromptNode(id="1", prompt="q1")
    a1 = AssistantNode(id="2", text="a1")
    u2 = UserPromptNode(id="3", prompt="q2")
    tc = AssistantNode(id="4", tool_calls={"c": {"tool_name": "t", "arguments": {}}})
    tr = ToolResultNode(id="5", results={"c": {"status": "ok", "content": "r"}})
    u3 = UserPromptNode(id="6", prompt="q3")
    a3 = AssistantNode(id="7", text="a3")

    nodes = [u1, a1, u2, tc, tr, u3, a3]
    turns = _split_into_turns(nodes)

    assert len(turns) == 3

    # Each turn must start with a UserPromptNode
    for turn in turns:
        assert isinstance(turn[0], UserPromptNode)

    # Verify correct grouping
    assert turns[0] == [u1, a1]
    assert turns[1] == [u2, tc, tr]
    assert turns[2] == [u3, a3]


# ---------------------------------------------------------------------------
# 6. Concurrent gather — backend called once per compressed turn
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compress_concurrent_gather() -> None:
    """Backend.generate is called exactly once per turn being compressed."""
    k = 3
    total_turns = 6
    compressible = total_turns - k  # = 3

    backend = MockBackend(
        [
            BackendTurnResult(output_text=f"sum{i}", tool_calls=[], finish_reason="completed")
            for i in range(compressible)
        ]
    )
    compressor = LLMCompressor(backend, keep_turns=k)

    messages: list[Node] = []
    for i in range(total_turns):
        _make_turn(messages, f"t{i}")

    summary, remaining = await compressor.compress(messages)
    assert summary != ""

    # backend._index advances by 1 for each generate() call consumed
    assert backend._index == compressible


# ---------------------------------------------------------------------------
# 7. all-or-nothing: backend failure propagates, original messages unchanged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compress_all_or_nothing_on_failure() -> None:
    """If backend raises, compress propagates the exception."""

    class FailingBackend(MockBackend):
        async def _gen(self, session: object):  # type: ignore[override]
            raise RuntimeError("backend exploded")
            yield  # pragma: no cover

    backend = FailingBackend()
    compressor = LLMCompressor(backend, keep_turns=3)

    messages: list[Node] = []
    for i in range(5):
        _make_turn(messages, f"t{i}")

    with pytest.raises(RuntimeError, match="backend exploded"):
        await compressor.compress(messages)


# ---------------------------------------------------------------------------
# 8. keep_turns < 1 is forced to 1 with a warning
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_keep_turns_below_1_forced_to_1() -> None:
    """keep_turns=0 emits a warning and behaves like keep_turns=1."""
    backend = MockBackend(
        [
            BackendTurnResult(output_text="sum1", tool_calls=[], finish_reason="completed"),
            BackendTurnResult(output_text="sum2", tool_calls=[], finish_reason="completed"),
        ]
    )

    with patch.object(logging.getLogger("little_agent.agent.compressor"), "warning") as mock_warn:
        compressor = LLMCompressor(backend, keep_turns=0)
        mock_warn.assert_called_once()
        assert "keep_turns" in mock_warn.call_args[0][0] or "0" in str(mock_warn.call_args)

    # 3 turns with effective keep_turns=1: 2 turns compressed, 1 kept
    messages: list[Node] = []
    for i in range(3):
        _make_turn(messages, f"t{i}")

    summary, remaining = await compressor.compress(messages)
    assert summary != ""
    assert _count_turns(remaining) == 1


# ---------------------------------------------------------------------------
# 9. Preserved nodes keep type and content
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compress_preserved_nodes_keep_content() -> None:
    """Preserved nodes keep their type and content intact."""
    k = 3
    backend = MockBackend(
        [
            BackendTurnResult(
                output_text="compressed-t0", tool_calls=[], finish_reason="completed"
            ),
            BackendTurnResult(
                output_text="compressed-t1", tool_calls=[], finish_reason="completed"
            ),
        ]
    )
    compressor = LLMCompressor(backend, keep_turns=k)

    prompts = [f"question-{i}" for i in range(5)]
    replies = [f"answer-{i}" for i in range(5)]

    messages: list[Node] = []
    for i in range(5):
        _make_turn(messages, f"t{i}", prompt=prompts[i], reply=replies[i])

    summary, remaining = await compressor.compress(messages)
    assert summary != ""

    # Remaining nodes must be the last k turns with original content intact
    user_nodes = [n for n in remaining if isinstance(n, UserPromptNode)]
    assert len(user_nodes) == k
    # Verify last k turn prompts
    for i, user_node in enumerate(user_nodes):
        assert user_node.prompt == prompts[2 + i]


# ---------------------------------------------------------------------------
# 10. _nodes_to_text includes tool nodes
# ---------------------------------------------------------------------------


def test_nodes_to_text_includes_tool_nodes() -> None:
    """_nodes_to_text formats tool call/result nodes correctly."""
    nodes: list[Node] = [
        UserPromptNode(id="1", prompt="run tool"),
        AssistantNode(
            id="2",
            tool_calls={"c1": {"tool_name": "echo", "arguments": {"text": "hi"}}},
        ),
        ToolResultNode(
            id="3",
            results={"c1": {"status": "completed", "content": "hi"}},
        ),
    ]
    text = _nodes_to_text(nodes)
    assert "run tool" in text
    assert "echo" in text
    assert "completed" in text


# ---------------------------------------------------------------------------
# 11. _nodes_to_text includes AssistantNode.text (pre-tool reasoning)
# ---------------------------------------------------------------------------


def test_nodes_to_text_includes_tool_call_output_text() -> None:
    """_nodes_to_text prepends 'Assistant: <text>' before tool-call line when non-empty."""
    nodes_with_text: list[Node] = [
        UserPromptNode(id="1", prompt="run tool"),
        AssistantNode(
            id="2",
            text="I will use bash",
            tool_calls={"c1": {"tool_name": "bash", "arguments": {"cmd": "ls"}}},
        ),
    ]
    text = _nodes_to_text(nodes_with_text)
    lines = text.splitlines()
    assert any(line.startswith("Assistant: I will use bash") for line in lines), (
        f"Expected 'Assistant: I will use bash' line, got: {lines}"
    )
    assert any("[Tool calls:" in line for line in lines), (
        f"Expected '[Tool calls:' line, got: {lines}"
    )
    assistant_idx = next(
        i for i, line in enumerate(lines) if line.startswith("Assistant: I will use bash")
    )
    tool_idx = next(i for i, line in enumerate(lines) if "[Tool calls:" in line)
    assert assistant_idx < tool_idx


# ---------------------------------------------------------------------------
# 12. _CompressorSession has id attribute (regression for AttributeError)
# ---------------------------------------------------------------------------


def test_compressor_session_has_id() -> None:
    """_CompressorSession must expose an 'id' attribute required by backends."""
    session = _CompressorSession("test prompt")
    assert hasattr(session, "id")
    assert isinstance(session.id, str)
    assert len(session.id) > 0


@pytest.mark.asyncio
async def test_compressor_session_id_passed_to_backend() -> None:
    """Backend receives a session with a valid id during summarization."""
    backend = MockBackend(
        [BackendTurnResult(output_text="summary", tool_calls=[], finish_reason="completed")]
    )
    compressor = LLMCompressor(backend, keep_turns=3)

    messages: list[Node] = []
    for i in range(4):
        _make_turn(messages, f"t{i}")

    await compressor.compress(messages)

    assert len(backend.sessions) == 1
    passed_session = backend.sessions[0]
    assert hasattr(passed_session, "id")
    assert isinstance(passed_session.id, str)
    assert len(passed_session.id) > 0


def test_nodes_to_text_tool_call_no_output_text() -> None:
    """_nodes_to_text omits 'Assistant:' line when text is empty."""
    nodes_no_text: list[Node] = [
        UserPromptNode(id="1", prompt="run tool"),
        AssistantNode(
            id="2",
            tool_calls={"c1": {"tool_name": "bash", "arguments": {"cmd": "ls"}}},
        ),
    ]
    text = _nodes_to_text(nodes_no_text)
    lines = text.splitlines()
    assert not any(line.startswith("Assistant:") for line in lines), (
        f"Expected no 'Assistant:' line when output_text is empty, got: {lines}"
    )
    assert any("[Tool calls:" in line for line in lines), (
        f"Expected '[Tool calls:' line, got: {lines}"
    )
