"""LLM-based session history compressor."""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING, Any

from little_agent.agent.nodes import (
    AssistantResponseNode,
    Node,
    SummaryNode,
    ToolCallNode,
    ToolResultNode,
    UserPromptNode,
)
from little_agent.backends.protocol import BackendTurnResult

if TYPE_CHECKING:
    from little_agent.backends.protocol import Backend


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
            parts.append(f"[Tool calls: {calls_str}]")
        elif isinstance(n, ToolResultNode):
            results_str = json.dumps(n.results, ensure_ascii=False)
            parts.append(f"[Tool results: {results_str}]")
        elif isinstance(n, SummaryNode):
            parts.append(f"[Previous summary: {n.summary}]")
    return "\n".join(parts)


class _CompressorSession:
    """Minimal session stub for issuing a single backend call."""

    def __init__(self, backend: Backend, prompt: str) -> None:
        self.tail: Node = UserPromptNode(id=str(uuid.uuid4()), prev=None, prompt=prompt)
        self._backend = backend
        self.agent: _CompressorAgent

    def _set_agent(self, agent: _CompressorAgent) -> None:
        self.agent = agent


class _CompressorAgent:
    """Minimal agent stub providing empty tools to the compressor session."""

    def __init__(self, backend: Backend) -> None:
        from little_agent.tools.manager import ToolManager

        self.backend = backend
        self.tools = ToolManager()
        self.client: Any = None
        self.compressor: Any = None


class LLMCompressor:
    """Compresses session history using an LLM backend.

    Keeps the most recent ``keep_nodes`` nodes verbatim; summarizes
    everything older than that into a single SummaryNode.
    """

    def __init__(self, backend: Backend, keep_nodes: int = 10) -> None:
        self._backend = backend
        self._keep_nodes = keep_nodes

    async def compress(self, head: Node | None) -> Node | None:
        if head is None:
            return None

        # Collect chain in chronological order
        chain: list[Node] = []
        node: Node | None = head
        while node is not None:
            chain.append(node)
            node = node.prev
        chain.reverse()

        if len(chain) <= self._keep_nodes:
            return head

        split = len(chain) - self._keep_nodes
        old_nodes = chain[:split]
        recent_nodes = chain[split:]

        summary_text = await self._summarize(old_nodes)
        summary_node = SummaryNode(
            id=str(uuid.uuid4()),
            prev=None,
            summary=summary_text,
        )

        # Relink recent nodes behind the summary node
        prev: Node = summary_node
        for n in recent_nodes:
            n.prev = prev
            prev = n

        return prev

    async def _summarize(self, nodes: list[Node]) -> str:
        history = _nodes_to_text(nodes)
        prompt = (
            "Please summarize the following conversation history concisely, "
            "preserving all important facts, decisions, and context:\n\n" + history
        )
        agent = _CompressorAgent(self._backend)
        session = _CompressorSession(self._backend, prompt)
        session._set_agent(agent)
        final: BackendTurnResult | None = None
        async for item in self._backend.generate(session):  # type: ignore[arg-type]
            if isinstance(item, BackendTurnResult):
                final = item
        if final is None:
            raise RuntimeError("Backend returned no result")
        return final.output_text
