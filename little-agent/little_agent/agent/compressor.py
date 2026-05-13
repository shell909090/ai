"""LLM-based session history compressor."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import TYPE_CHECKING, Protocol

from little_agent.agent.nodes import (
    AssistantNode,
    Node,
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

    async def compress(self, messages: list[Node]) -> tuple[str, list[Node]]: ...


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

    async def compress(self, messages: list[Node]) -> tuple[str, list[Node]]:
        """Compress old turns into a single summary string; return (summary, preserve_zone)."""
        if not messages:
            return "", messages

        t0 = time.monotonic()

        # Find preserve-zone start based on keep_turns
        user_indices = [i for i, n in enumerate(messages) if isinstance(n, UserPromptNode)]
        if len(user_indices) <= self._keep_turns:
            logger.info(
                "compress: skipped — only %d user turns, keep_turns=%d",
                len(user_indices),
                self._keep_turns,
            )
            return "", messages

        preserve_start_idx = user_indices[-self._keep_turns]
        compress_zone = messages[:preserve_start_idx]
        preserve_zone = messages[preserve_start_idx:]

        if not compress_zone:
            return "", messages

        # Split compress_zone into turns and summarize concurrently
        turns = _split_into_turns(compress_zone)
        if not turns:
            return "", messages

        summary_texts: list[str] = await asyncio.gather(*[self._summarize(t) for t in turns])
        combined_summary = "\n\n".join(summary_texts)

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            "compress: compressed_turns=%d elapsed_ms=%d",
            len(turns),
            elapsed_ms,
        )

        return combined_summary, list(preserve_zone)

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
