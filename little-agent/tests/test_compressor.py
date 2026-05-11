"""Tests for LLMCompressor (T38)."""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

from little_agent.agent.compressor import (
    LLMCompressor,
    _CompressorSession,
    _apply_w_limit,
    _nodes_to_text,
    _split_into_turns,
)
from little_agent.agent.nodes import (
    AssistantResponseNode,
    Node,
    SummaryNode,
    ToolCallNode,
    ToolResultNode,
    UserPromptNode,
)
from little_agent.backends.protocol import BackendTurnResult
from tests.mocks import MockBackend

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_turn(
    turn_id: str,
    prev: Node | None,
    prompt: str = "user msg",
    reply: str = "assistant reply",
) -> AssistantResponseNode:
    """Build a single (UserPromptNode, AssistantResponseNode) turn and return the tail."""
    u = UserPromptNode(id=f"{turn_id}-u", prev=prev, prompt=prompt)
    a = AssistantResponseNode(id=f"{turn_id}-a", prev=u, text=reply)
    return a


def _chain_to_list(tail: Node | None) -> list[Node]:
    """Walk tail→head via .prev and return list in chronological order."""
    nodes: list[Node] = []
    n = tail
    while n is not None:
        nodes.append(n)
        n = n.prev
    nodes.reverse()
    return nodes


def _count_turns(nodes: list[Node]) -> int:
    """Count the number of UserPromptNodes in a list (= number of turns)."""
    return sum(1 for n in nodes if isinstance(n, UserPromptNode))


# ---------------------------------------------------------------------------
# 1. compress(None) → None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compress_none_returns_none() -> None:
    """compress(None) must return None without calling the backend."""
    backend = MockBackend()
    compressor = LLMCompressor(backend, keep_turns=3)
    result = await compressor.compress(None)
    assert result is None
    # backend was never called
    assert backend._index == 0


# ---------------------------------------------------------------------------
# 2. Not enough turns → return tail unchanged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compress_not_enough_turns_unchanged() -> None:
    """With exactly K turns in the chain, compress returns the original tail."""
    backend = MockBackend()
    compressor = LLMCompressor(backend, keep_turns=3)

    # Build exactly 3 turns
    tail: Node = _make_turn("t1", None)
    tail = _make_turn("t2", tail)
    tail = _make_turn("t3", tail)
    original_tail = tail

    result = await compressor.compress(tail)
    assert result is original_tail
    # backend was never called
    assert backend._index == 0


# ---------------------------------------------------------------------------
# 3. Upper bound is the last SummaryNode — content before it is not re-compressed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compress_identifies_upper_bound_summary_node() -> None:
    """The existing SummaryNode acts as the upper bound; nodes before it are untouched."""
    # script: one summary per compressible turn (only 1 turn beyond the summary is compressible)
    backend = MockBackend(
        [BackendTurnResult(output_text="new-summary", tool_calls=[], finish_reason="completed")]
    )
    compressor = LLMCompressor(backend, keep_turns=3)

    # old_summary → turn_old (1 turn before summary boundary) → 3 kept turns
    # Layout: [old_summary] [turn_old] [turn_k1] [turn_k2] [turn_k3]
    # compress_start = index_of(old_summary) + 1
    # turns after compress_start = turn_old, turn_k1, turn_k2, turn_k3 = 4 turns
    # keep_turns=3 → turn_old is compressible (1 turn), turn_k1/k2/k3 preserved

    old_summary = SummaryNode(id="s0", prev=None, summary="old content")
    tail: Node = _make_turn("t_old", old_summary)
    tail = _make_turn("t_k1", tail)
    tail = _make_turn("t_k2", tail)
    tail = _make_turn("t_k3", tail)

    result = await compressor.compress(tail)
    assert result is not None

    chain = _chain_to_list(result)

    # The very first node must be the old_summary (unchanged)
    assert chain[0] is old_summary

    # The second node must be the new SummaryNode produced from turn_old
    assert isinstance(chain[1], SummaryNode)
    assert chain[1].summary == "new-summary"

    # The old summary text must NOT appear in the new summary (backend was only called once)
    assert backend._index == 1


# ---------------------------------------------------------------------------
# 4. No SummaryNode → upper bound is chain head
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compress_upper_bound_is_chain_head_when_no_summary_node() -> None:
    """Without any SummaryNode, all turns outside the keep-zone are compressed."""
    backend = MockBackend(
        [
            BackendTurnResult(output_text="s1", tool_calls=[], finish_reason="completed"),
            BackendTurnResult(output_text="s2", tool_calls=[], finish_reason="completed"),
        ]
    )
    compressor = LLMCompressor(backend, keep_turns=3)

    # 5 turns total, no SummaryNode → 2 turns compressed, 3 kept
    tail: Node | None = None
    for i in range(5):
        tail = _make_turn(f"t{i}", tail)
    assert tail is not None

    result = await compressor.compress(tail)
    assert result is not None

    chain = _chain_to_list(result)

    # First two nodes should be new SummaryNodes (one per compressed turn)
    assert isinstance(chain[0], SummaryNode)
    assert isinstance(chain[1], SummaryNode)

    # Remaining 3 turns preserved
    preserved = chain[2:]
    assert _count_turns(preserved) == 3


# ---------------------------------------------------------------------------
# 5. Exactly K turns preserved after compression
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

    tail: Node | None = None
    for i in range(total_turns):
        tail = _make_turn(f"t{i}", tail)
    assert tail is not None

    result = await compressor.compress(tail)
    assert result is not None

    chain = _chain_to_list(result)

    # Tail portion (after all SummaryNodes) must have exactly k turns
    # Find last SummaryNode index
    last_summary_pos = -1
    for idx, n in enumerate(chain):
        if isinstance(n, SummaryNode):
            last_summary_pos = idx

    preserved = chain[last_summary_pos + 1 :]
    assert _count_turns(preserved) == k


# ---------------------------------------------------------------------------
# 6. _split_into_turns correctness
# ---------------------------------------------------------------------------


def test_compress_splits_turns_correctly() -> None:
    """_split_into_turns groups nodes so each turn starts with a UserPromptNode."""
    u1 = UserPromptNode(id="1", prev=None, prompt="q1")
    a1 = AssistantResponseNode(id="2", prev=u1, text="a1")
    u2 = UserPromptNode(id="3", prev=a1, prompt="q2")
    tc = ToolCallNode(id="4", prev=u2, calls={"c": {"tool_name": "t", "arguments": {}}})
    tr = ToolResultNode(id="5", prev=tc, results={"c": {"status": "ok", "content": "r"}})
    u3 = UserPromptNode(id="6", prev=tr, prompt="q3")
    a3 = AssistantResponseNode(id="7", prev=u3, text="a3")

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
# 7. Concurrent gather — backend called once per compressed turn
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

    tail: Node | None = None
    for i in range(total_turns):
        tail = _make_turn(f"t{i}", tail)
    assert tail is not None

    result = await compressor.compress(tail)
    assert result is not None

    # backend._index advances by 1 for each generate() call consumed
    assert backend._index == compressible


# ---------------------------------------------------------------------------
# 8. all-or-nothing: backend failure propagates, original tail unchanged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compress_all_or_nothing_on_failure() -> None:
    """If backend raises, compress propagates the exception; original chain is untouched."""

    class FailingBackend(MockBackend):
        async def _gen(self, session: object):  # type: ignore[override]
            raise RuntimeError("backend exploded")
            # make it a generator
            yield  # pragma: no cover

    backend = FailingBackend()
    compressor = LLMCompressor(backend, keep_turns=3)

    # Build 5 turns so that 2 turns need compression
    tail: Node | None = None
    for i in range(5):
        tail = _make_turn(f"t{i}", tail)
    assert tail is not None
    original_tail = tail

    with pytest.raises(RuntimeError, match="backend exploded"):
        await compressor.compress(tail)

    # Original tail must not have been modified
    assert tail is original_tail


# ---------------------------------------------------------------------------
# 9. _apply_w_limit trims old summaries
# ---------------------------------------------------------------------------


def test_apply_w_limit_trims_old_summaries() -> None:
    """When cumulative token count exceeds W, old SummaryNodes are discarded.

    4 SummaryNodes, each with a 400-char ASCII summary.
    New formula: len(text.encode('utf-8')) // 3 = 400 // 3 = 133 tokens each.
    w_tokens=133: newest node cumulative=133 (not >133); second tips to 266 (>133)
    → cutoff at index 2 → discard indices 0,1 → discarded_count=2.
    """
    summary_text = "x" * 400  # 400 ASCII bytes → 400 // 3 = 133 tokens

    s0 = SummaryNode(id="s0", prev=None, summary=summary_text)
    s1 = SummaryNode(id="s1", prev=s0, summary=summary_text)
    s2 = SummaryNode(id="s2", prev=s1, summary=summary_text)
    s3 = SummaryNode(id="s3", prev=s2, summary=summary_text)

    chain = [s0, s1, s2, s3]
    discarded, trimmed = _apply_w_limit(chain, w_tokens=133)

    assert discarded == 2
    assert len(trimmed) == 2
    assert trimmed[0] is s2
    assert trimmed[1] is s3


# ---------------------------------------------------------------------------
# 10. _apply_w_limit: no trim when under limit
# ---------------------------------------------------------------------------


def test_apply_w_limit_no_trim_when_under_limit() -> None:
    """When total tokens fit within W, nothing is discarded."""
    summary_text = "x" * 40  # 40 chars → 10 tokens each

    s0 = SummaryNode(id="s0", prev=None, summary=summary_text)
    s1 = SummaryNode(id="s1", prev=s0, summary=summary_text)

    chain = [s0, s1]
    discarded, trimmed = _apply_w_limit(chain, w_tokens=1000)

    assert discarded == 0
    assert trimmed is chain


# ---------------------------------------------------------------------------
# 11. _apply_w_limit: zero means no limit
# ---------------------------------------------------------------------------


def test_apply_w_limit_zero_means_no_limit() -> None:
    """w_tokens=0 disables the limit; chain is returned as-is."""
    summary_text = "z" * 10000  # very large

    s0 = SummaryNode(id="s0", prev=None, summary=summary_text)
    s1 = SummaryNode(id="s1", prev=s0, summary=summary_text)

    chain = [s0, s1]
    discarded, trimmed = _apply_w_limit(chain, w_tokens=0)

    assert discarded == 0
    assert trimmed is chain


# ---------------------------------------------------------------------------
# 12. keep_turns < 1 is forced to 1 with a warning
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
    tail: Node | None = None
    for i in range(3):
        tail = _make_turn(f"t{i}", tail)
    assert tail is not None

    result = await compressor.compress(tail)
    assert result is not None
    chain = _chain_to_list(result)
    assert _count_turns(chain) == 1


# ---------------------------------------------------------------------------
# 13. Compressed turns become SummaryNodes; preserved nodes are unchanged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compress_produces_summary_nodes() -> None:
    """Each compressed turn becomes a SummaryNode; preserved nodes keep type and content."""
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

    tail: Node | None = None
    for i in range(5):
        tail = _make_turn(f"t{i}", tail, prompt=prompts[i], reply=replies[i])
    assert tail is not None

    result = await compressor.compress(tail)
    assert result is not None

    chain = _chain_to_list(result)

    # First two nodes must be SummaryNodes from compressed turns
    assert isinstance(chain[0], SummaryNode)
    assert isinstance(chain[1], SummaryNode)
    assert chain[0].summary == "compressed-t0"
    assert chain[1].summary == "compressed-t1"

    # Remaining nodes must be the last k turns with original content intact
    preserved = chain[2:]
    user_nodes = [n for n in preserved if isinstance(n, UserPromptNode)]
    assert len(user_nodes) == k
    # Verify last k turn prompts
    for i, user_node in enumerate(user_nodes):
        assert user_node.prompt == prompts[2 + i]


# ---------------------------------------------------------------------------
# 14. _nodes_to_text includes tool nodes (kept from original test suite)
# ---------------------------------------------------------------------------


def test_nodes_to_text_includes_tool_nodes() -> None:
    """_nodes_to_text formats tool call/result nodes correctly."""
    nodes: list[Node] = [
        UserPromptNode(id="1", prev=None, prompt="run tool"),
        ToolCallNode(
            id="2",
            prev=None,
            calls={"c1": {"tool_name": "echo", "arguments": {"text": "hi"}}},
        ),
        ToolResultNode(
            id="3",
            prev=None,
            results={"c1": {"status": "completed", "content": "hi"}},
        ),
    ]
    text = _nodes_to_text(nodes)
    assert "run tool" in text
    assert "echo" in text
    assert "completed" in text


# ---------------------------------------------------------------------------
# 15. _nodes_to_text includes ToolCallNode.output_text
# ---------------------------------------------------------------------------


def test_nodes_to_text_includes_tool_call_output_text() -> None:
    """_nodes_to_text prepends 'Assistant: <output_text>' before tool-call line when non-empty."""
    nodes_with_text: list[Node] = [
        UserPromptNode(id="1", prev=None, prompt="run tool"),
        ToolCallNode(
            id="2",
            prev=None,
            output_text="I will use bash",
            calls={"c1": {"tool_name": "bash", "arguments": {"cmd": "ls"}}},
        ),
    ]
    text = _nodes_to_text(nodes_with_text)
    lines = text.splitlines()
    # There should be a line starting with "Assistant: I will use bash"
    assert any(line.startswith("Assistant: I will use bash") for line in lines), (
        f"Expected 'Assistant: I will use bash' line, got: {lines}"
    )
    # There should also be a tool-call line
    assert any("[Tool calls:" in line for line in lines), (
        f"Expected '[Tool calls:' line, got: {lines}"
    )
    # The assistant line must appear before the tool-call line
    assistant_idx = next(
        i for i, line in enumerate(lines) if line.startswith("Assistant: I will use bash")
    )
    tool_idx = next(i for i, line in enumerate(lines) if "[Tool calls:" in line)
    assert assistant_idx < tool_idx


# ---------------------------------------------------------------------------
# 16. _CompressorSession has id attribute (regression for AttributeError)
# ---------------------------------------------------------------------------


def test_compressor_session_has_id() -> None:
    """_CompressorSession must expose an 'id' attribute required by backends."""
    from little_agent.backends.protocol import Backend

    backend = MockBackend()
    session = _CompressorSession(backend, "test prompt")  # type: ignore[arg-type]
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

    tail: Node | None = None
    for i in range(4):
        tail = _make_turn(f"t{i}", tail)
    assert tail is not None

    await compressor.compress(tail)

    assert len(backend.sessions) == 1
    passed_session = backend.sessions[0]
    assert hasattr(passed_session, "id")
    assert isinstance(passed_session.id, str)
    assert len(passed_session.id) > 0


def test_nodes_to_text_tool_call_no_output_text() -> None:
    """_nodes_to_text omits 'Assistant:' line when output_text is empty."""
    nodes_no_text: list[Node] = [
        UserPromptNode(id="1", prev=None, prompt="run tool"),
        ToolCallNode(
            id="2",
            prev=None,
            output_text="",
            calls={"c1": {"tool_name": "bash", "arguments": {"cmd": "ls"}}},
        ),
    ]
    text = _nodes_to_text(nodes_no_text)
    lines = text.splitlines()
    # No assistant line (the User prompt line starts with "User:", not "Assistant:")
    assert not any(line.startswith("Assistant:") for line in lines), (
        f"Expected no 'Assistant:' line when output_text is empty, got: {lines}"
    )
    # The tool-call line must still be present
    assert any("[Tool calls:" in line for line in lines), (
        f"Expected '[Tool calls:' line, got: {lines}"
    )
