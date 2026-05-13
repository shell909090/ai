"""LLM-based session history compressor."""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import time
import uuid
from typing import TYPE_CHECKING, Protocol

from little_agent.agent.nodes import (
    AssistantResponseNode,
    Node,
    SummaryNode,
    ToolCallNode,
    ToolResultNode,
    UserPromptNode,
)
from little_agent.backends.protocol import BackendTurnResult
from little_agent.tools.protocol import ToolMap

if TYPE_CHECKING:
    from little_agent.backends.protocol import Backend

logger = logging.getLogger(__name__)


class Compressor(Protocol):
    """Compressor protocol; LLMCompressor below is the sole built-in impl."""

    async def compress(self, head: Node | None) -> Node | None: ...


def _nodes_to_text(nodes: list[Node]) -> str:
    """Format a list of nodes as readable conversation history."""
    parts: list[str] = []
    for n in nodes:
        if isinstance(n, UserPromptNode):
            prompt = n.prompt if isinstance(n.prompt, str) else json.dumps(n.prompt)
            parts.append(f"User: {prompt}")
        elif isinstance(n, AssistantResponseNode):
            parts.append(f"Assistant: {n.text}")
        elif isinstance(n, ToolCallNode):
            calls_str = json.dumps(n.calls, ensure_ascii=False)
            if n.output_text:
                parts.append(f"Assistant: {n.output_text}")
            parts.append(f"[Tool calls: {calls_str}]")
        elif isinstance(n, ToolResultNode):
            results_str = json.dumps(n.results, ensure_ascii=False)
            parts.append(f"[Tool results: {results_str}]")
        elif isinstance(n, SummaryNode):
            parts.append(f"[Previous summary: {n.summary}]")
    return "\n".join(parts)


def _split_into_turns(nodes: list[Node]) -> list[list[Node]]:
    """Split nodes into turns; each turn starts with a UserPromptNode."""
    turns: list[list[Node]] = []
    current: list[Node] = []
    for n in nodes:
        if isinstance(n, UserPromptNode) and current:
            turns.append(current)
            current = [n]
        else:
            current.append(n)
    if current:
        turns.append(current)
    return turns


def _apply_w_limit(chain: list[Node], w_tokens: int) -> tuple[int, list[Node]]:
    """Trim old SummaryNodes when cumulative tokens exceed W.

    Returns (discarded_count, trimmed_chain).
    w_tokens=0 means no limit; returns (0, chain) immediately.
    """
    if w_tokens == 0:
        return 0, chain

    # Collect indices of SummaryNodes
    summary_indices = [i for i, n in enumerate(chain) if isinstance(n, SummaryNode)]
    if not summary_indices:
        return 0, chain

    # Accumulate token estimates from newest SummaryNode backwards
    cumulative = 0
    cutoff_idx: int | None = None
    for idx in reversed(summary_indices):
        node = chain[idx]
        assert isinstance(node, SummaryNode)
        cumulative += len(str(node.summary).encode("utf-8")) // 3
        if cumulative > w_tokens:
            # Discard everything before this node (this node itself is kept)
            cutoff_idx = idx
            break

    if cutoff_idx is None:
        return 0, chain

    # Count discarded SummaryNodes (those before cutoff_idx)
    discarded_count = sum(1 for i in summary_indices if i < cutoff_idx)
    return discarded_count, chain[cutoff_idx:]


class _CompressorSession:
    """Minimal BackendSession for a single-prompt backend call with no tools."""

    def __init__(self, prompt: str) -> None:
        self.id: str = str(uuid.uuid4())
        self.tail: Node | None = UserPromptNode(id=str(uuid.uuid4()), prev=None, prompt=prompt)

    def get_turn_tool_map(self) -> ToolMap:
        """Return empty ToolMap — compressor sessions have no tools."""
        return {}


class LLMCompressor:
    """Compresses session history using an LLM backend.

    Keeps the most recent ``keep_turns`` turns verbatim; summarizes
    older turns into SummaryNodes. Old SummaryNodes are trimmed when
    their cumulative size exceeds ``compressed_window_tokens``.
    """

    def __init__(
        self,
        backend: Backend,
        keep_turns: int = 3,
        compressed_window_tokens: int = 0,
    ) -> None:
        """Initialize LLMCompressor with backend and tuning parameters."""
        if keep_turns < 1:
            logger.warning("keep_turns=%d is too small; forcing to 1", keep_turns)
            keep_turns = 1
        self._backend = backend
        self._keep_turns = keep_turns
        self._compressed_window_tokens = compressed_window_tokens

    async def compress(self, tail: Node | None) -> Node | None:
        """Compress session history by summarizing old turns into SummaryNodes."""
        if tail is None:
            return None

        t0 = time.monotonic()

        # Step 1: collect chain in chronological order
        chain: list[Node] = []
        node: Node | None = tail
        while node is not None:
            chain.append(node)
            node = node.prev
        chain.reverse()

        # Step 2: find compress-zone upper bound (last SummaryNode index)
        upper_bound_idx = -1
        for i, n in enumerate(chain):
            if isinstance(n, SummaryNode):
                upper_bound_idx = i
        compress_start = upper_bound_idx + 1

        # Step 3: find preserve-zone start (based on keep_turns)
        user_indices = [
            i
            for i, n in enumerate(chain[compress_start:], start=compress_start)
            if isinstance(n, UserPromptNode)
        ]
        if len(user_indices) <= self._keep_turns:
            logger.info(
                "compress: skipped — only %d user turns, keep_turns=%d",
                len(user_indices),
                self._keep_turns,
            )
            return tail
        preserve_start_idx = user_indices[-self._keep_turns]
        if preserve_start_idx <= compress_start:
            logger.info("compress: skipped — no nodes between summary boundary and preserve zone")
            return tail

        # Step 4: split zones
        head_part = chain[:compress_start]
        compress_zone = chain[compress_start:preserve_start_idx]
        preserve_zone = chain[preserve_start_idx:]

        # Step 5: split compress_zone into turns
        turns = _split_into_turns(compress_zone)
        if not turns:
            return tail

        # Step 6: concurrent summarization (all-or-nothing)
        summary_texts: list[str] = await asyncio.gather(*[self._summarize(t) for t in turns])

        # Step 7: assemble new chain
        new_summary_nodes: list[Node] = [
            SummaryNode(id=str(uuid.uuid4()), prev=None, summary=text) for text in summary_texts
        ]
        new_chain = head_part + new_summary_nodes + preserve_zone

        # Step 8: apply W-limit
        discarded, new_chain = _apply_w_limit(new_chain, self._compressed_window_tokens)

        # Step 9: relink prev pointers, copying shared nodes to avoid mutating
        # another session's chain (preserve_zone nodes may be shared via fork).
        prev_node: Node | None = None
        relinked: list[Node] = []
        for n in new_chain:
            if n.prev != prev_node:
                n = dataclasses.replace(n, prev=prev_node)
            relinked.append(n)
            prev_node = n
        new_tail = prev_node

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            "compress: compressed_turns=%d new_summaries=%d discarded_summaries=%d elapsed_ms=%d",
            len(turns),
            len(new_summary_nodes),
            discarded,
            elapsed_ms,
        )

        return new_tail

    async def _summarize(self, nodes: list[Node]) -> str:
        """Summarize a single conversation turn via the backend."""
        history = _nodes_to_text(nodes)
        prompt = (
            "Please summarize the following conversation turn, preserving important facts, "
            "decisions, tool interactions, and context in reasonable detail:\n\n" + history
        )
        session = _CompressorSession(prompt)
        final: BackendTurnResult | None = None
        async for item in self._backend.generate(session):
            if isinstance(item, BackendTurnResult):
                final = item
        if final is None:
            raise RuntimeError("Backend returned no result")
        return final.output_text
