"""Tests for LLMCompressor."""

from __future__ import annotations

import pytest

from little_agent.agent.nodes import (
    AssistantResponseNode,
    SummaryNode,
    ToolCallNode,
    ToolResultNode,
    UserPromptNode,
)
from little_agent.backends.protocol import BackendTurnResult
from little_agent.compressor import LLMCompressor
from tests.mocks import MockBackend


def _make_chain(*texts: str) -> AssistantResponseNode | UserPromptNode:
    """Build a simple alternating user/assistant chain and return the tail."""
    prev = None
    node = None
    for i, text in enumerate(texts):
        if i % 2 == 0:
            node = UserPromptNode(id=str(i), prev=prev, prompt=text)
        else:
            node = AssistantResponseNode(id=str(i), prev=prev, text=text)
        prev = node
    return node  # type: ignore[return-value]


@pytest.mark.asyncio
async def test_compress_short_chain_unchanged() -> None:
    """Chain shorter than keep_nodes is returned unchanged."""
    backend = MockBackend()
    compressor = LLMCompressor(backend, keep_nodes=10)
    head = _make_chain("hi", "hello", "how are you", "fine")
    result = await compressor.compress(head)
    assert result is head


@pytest.mark.asyncio
async def test_compress_none_returns_none() -> None:
    """None input returns None."""
    backend = MockBackend()
    compressor = LLMCompressor(backend, keep_nodes=10)
    result = await compressor.compress(None)
    assert result is None


@pytest.mark.asyncio
async def test_compress_long_chain_creates_summary_node() -> None:
    """Chain longer than keep_nodes produces a SummaryNode at the front."""
    backend = MockBackend(
        [BackendTurnResult(output_text="Summary text", tool_calls=[], finish_reason="completed")]
    )
    compressor = LLMCompressor(backend, keep_nodes=2)
    # Build 6-node chain (3 user + 3 assistant turns)
    head = _make_chain("q1", "a1", "q2", "a2", "q3", "a3")
    result = await compressor.compress(head)

    assert result is not None
    # Walk to the oldest node — should be a SummaryNode
    node = result
    while node.prev is not None:
        node = node.prev
    assert isinstance(node, SummaryNode)
    assert node.summary == "Summary text"


@pytest.mark.asyncio
async def test_compress_keeps_recent_nodes() -> None:
    """After compression, the most recent keep_nodes nodes are preserved."""
    backend = MockBackend(
        [BackendTurnResult(output_text="Summary", tool_calls=[], finish_reason="completed")]
    )
    compressor = LLMCompressor(backend, keep_nodes=2)
    head = _make_chain("q1", "a1", "q2", "a2", "q3", "a3")

    result = await compressor.compress(head)
    assert result is not None

    chain: list = []
    node = result
    while node is not None:
        chain.append(node)
        node = node.prev
    chain.reverse()

    assert isinstance(chain[0], SummaryNode)
    assert len(chain) == 3  # SummaryNode + 2 recent nodes


@pytest.mark.asyncio
async def test_nodes_to_text_includes_tool_nodes() -> None:
    """_nodes_to_text formats tool call/result nodes."""
    from little_agent.compressor import _nodes_to_text

    nodes = [
        UserPromptNode(id="1", prev=None, prompt="run tool"),
        ToolCallNode(
            id="2", prev=None, calls={"c1": {"tool_name": "echo", "arguments": {"text": "hi"}}}
        ),
        ToolResultNode(id="3", prev=None, results={"c1": {"status": "completed", "content": "hi"}}),
    ]
    text = _nodes_to_text(nodes)
    assert "run tool" in text
    assert "echo" in text
    assert "completed" in text
