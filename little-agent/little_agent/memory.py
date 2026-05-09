"""Memory system for cross-session fact persistence."""

from __future__ import annotations

import json
import logging
from pathlib import Path
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
    from little_agent.agent.session import SessionCore
    from little_agent.backends.protocol import Backend

logger = logging.getLogger(__name__)


class Memory(Protocol):
    """Protocol for memory implementations."""

    async def remember(self, session: "SessionCore") -> None:
        """Extract and store key facts from the session."""
        ...

    async def recall(self) -> str:
        """Return current memory summary to inject into system prompt."""
        ...


def _nodes_to_text(head: Node | None) -> str:
    """Format chain nodes as readable conversation history."""
    parts: list[str] = []
    node = head
    chain: list[Node] = []
    while node is not None:
        chain.append(node)
        node = node.prev
    chain.reverse()

    for n in chain:
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


class _MemorySession:
    """Minimal session stub for memory extraction backend call."""

    def __init__(self, backend: Backend, prompt: str) -> None:
        self.tail: Node = UserPromptNode(id="mem-prompt", prev=None, prompt=prompt)
        self._backend = backend
        self.agent: _MemoryAgent

    def _set_agent(self, agent: _MemoryAgent) -> None:
        self.agent = agent

    def get_turn_tool_map(self) -> ToolMap:
        """Return empty ToolMap — memory sessions have no tools."""
        return {}


class _MemoryAgent:
    """Minimal agent stub providing empty tools to the memory session."""

    def __init__(self, backend: Backend) -> None:
        from little_agent.tools.manager import ToolManager

        self.backend = backend
        self.tools = ToolManager()
        self.client: object = None
        self.compressor: object = None


class FileMemory:
    """Memory implementation that persists facts to a JSON Lines file.

    Uses an LLM backend to extract key facts from session history.
    Facts are stored as JSON Lines and recalled as a bullet list.
    """

    def __init__(self, backend: Backend, path: str | Path) -> None:
        self._backend = backend
        self._path = Path(path)
        self._facts: list[str] = []
        self._load_facts()

    def _load_facts(self) -> None:
        """Load existing facts from file."""
        if not self._path.exists():
            return
        try:
            with open(self._path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        if isinstance(data, dict) and "fact" in data:
                            self._facts.append(str(data["fact"]))
                        elif isinstance(data, str):
                            self._facts.append(data)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            logger.exception("Failed to load memory file: %s", self._path)

    def _save_facts(self) -> None:
        """Save all facts to file as JSON Lines."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                for fact in self._facts:
                    f.write(json.dumps({"fact": fact}, ensure_ascii=False) + "\n")
        except OSError:
            logger.exception("Failed to save memory file: %s", self._path)

    async def remember(self, session: "SessionCore") -> None:
        """Extract key facts from session and append to memory."""
        history = _nodes_to_text(session.tail)
        if not history.strip():
            return

        prompt = (
            "Analyze the following conversation and extract any important facts, "
            "preferences, or context that should be remembered for future conversations. "
            "Return each fact on a separate line, prefixed with '- '. "
            "If there are no important facts to remember, respond with 'NONE'.\n\n" + history
        )

        agent = _MemoryAgent(self._backend)
        mem_session = _MemorySession(self._backend, prompt)
        mem_session._set_agent(agent)

        final: BackendTurnResult | None = None
        async for item in self._backend.generate(mem_session):  # type: ignore[arg-type]
            if isinstance(item, BackendTurnResult):
                final = item

        if final is None:
            logger.warning("Memory backend returned no result")
            return

        new_facts = self._parse_facts(final.output_text)
        if new_facts:
            self._facts.extend(new_facts)
            self._save_facts()
            logger.debug("Remembered %d new facts", len(new_facts))

    def _parse_facts(self, text: str) -> list[str]:
        """Parse fact lines from LLM output."""
        facts: list[str] = []
        for line in text.strip().splitlines():
            line = line.strip()
            if line.upper() == "NONE":
                continue
            if line.startswith("-"):
                facts.append(line[1:].strip())
            elif line:
                facts.append(line)
        return facts

    async def recall(self) -> str:
        """Return current memory summary as system prompt text."""
        if not self._facts:
            return ""
        lines = ["Important facts from previous conversations:"]
        for fact in self._facts:
            lines.append(f"- {fact}")
        return "\n".join(lines)
