"""LLM-based session history compressor."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import TYPE_CHECKING

from little_agent.agent.nodes import AssistantNode, ToolResultNode, UserPromptNode
from little_agent.backends.protocol import BackendTurnResult
from little_agent.tools.protocol import ToolMap
from little_agent.types import Node

if TYPE_CHECKING:
    from little_agent.backends.protocol import Backend

logger = logging.getLogger(__name__)

_MAX_COMPRESS_BATCHES = 3


def _nodes_to_text(nodes: list[Node]) -> str:
    """Format a list of nodes as readable conversation history."""
    parts: list[str] = []
    for n in nodes:
        if isinstance(n, UserPromptNode):
            prompt = n.prompt if isinstance(n.prompt, str) else json.dumps(n.prompt)
            parts.append(f"User: {prompt}")
        elif isinstance(n, AssistantNode):
            if n.text:
                parts.append(f"Assistant: {n.text}")
            if n.tool_calls:
                calls_str = json.dumps(n.tool_calls, ensure_ascii=False)
                parts.append(f"[Tool calls: {calls_str}]")
        elif isinstance(n, ToolResultNode):
            results_str = json.dumps(n.results, ensure_ascii=False)
            parts.append(f"[Tool results: {results_str}]")
    return "\n".join(parts)


def _batch_turns(turns: list[list[Node]], max_batches: int) -> list[list[Node]]:
    """Group turns into at most max_batches roughly equal flat node lists."""
    n = len(turns)
    if n == 0:
        return []
    k = min(n, max_batches)
    batches: list[list[Node]] = []
    start = 0
    for i in range(k):
        size = n // k + (1 if i < n % k else 0)
        batch_nodes: list[Node] = []
        for turn in turns[start : start + size]:
            batch_nodes.extend(turn)
        batches.append(batch_nodes)
        start += size
    return batches


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


class _CompressorSession:
    """Minimal BackendSession for a single-prompt backend call with no tools."""

    def __init__(self, prompt: str) -> None:
        self.id: str = str(uuid.uuid4())
        self.system_prompt: str | None = None
        self.summaries: list[str] = []
        self.messages: list[Node] = [UserPromptNode(id=str(uuid.uuid4()), prompt=prompt)]

    def get_turn_tool_map(self) -> ToolMap:
        """Return empty ToolMap — compressor sessions have no tools."""
        return {}


class LLMCompressor:
    """Compresses session history using an LLM backend.

    Keeps the most recent ``keep_turns`` turns verbatim; summarizes older turns.
    """

    def __init__(
        self,
        backend: Backend,
        keep_turns: int = 3,
    ) -> None:
        """Initialize LLMCompressor with backend and tuning parameters."""
        if keep_turns < 1:
            logger.warning("keep_turns=%d is too small; forcing to 1", keep_turns)
            keep_turns = 1
        self._backend = backend
        self._keep_turns = keep_turns

    async def compress(self, messages: list[Node]) -> tuple[list[str], list[Node]]:
        """Compress old turns into up to 3 summary strings; return (summaries, preserve_zone)."""
        if not messages:
            return [], messages

        t0 = time.monotonic()

        # Find preserve-zone start based on keep_turns
        user_indices = [i for i, n in enumerate(messages) if isinstance(n, UserPromptNode)]
        if len(user_indices) <= self._keep_turns:
            logger.info(
                "compress: skipped — only %d user turns, keep_turns=%d",
                len(user_indices),
                self._keep_turns,
            )
            return [], messages

        preserve_start_idx = user_indices[-self._keep_turns]
        compress_zone = messages[:preserve_start_idx]
        preserve_zone = messages[preserve_start_idx:]

        if not compress_zone:
            return [], messages

        turns = _split_into_turns(compress_zone)
        if not turns:
            return [], messages

        # Batch turns into at most MAX_COMPRESS_BATCHES groups.
        batches = _batch_turns(turns, _MAX_COMPRESS_BATCHES)
        total = len(batches)
        summary_texts: list[str] = await asyncio.gather(
            *[self._summarize(batch, i + 1, total) for i, batch in enumerate(batches)]
        )

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            "compress: total_turns=%d batches=%d summaries=%d elapsed_ms=%d",
            len(turns),
            total,
            len(summary_texts),
            elapsed_ms,
        )

        return list(summary_texts), list(preserve_zone)

    async def _summarize(self, nodes: list[Node], batch_num: int, total_batches: int) -> str:
        """Summarize a batch of conversation turns via the backend."""
        n_turns = sum(1 for n in nodes if isinstance(n, UserPromptNode))
        logger.info(
            "compress batch %d/%d start: %d turns, %d nodes",
            batch_num,
            total_batches,
            n_turns,
            len(nodes),
        )
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
        result = final.output_text
        logger.info(
            "compress batch %d/%d done: %d chars",
            batch_num,
            total_batches,
            len(result),
        )
        return result
