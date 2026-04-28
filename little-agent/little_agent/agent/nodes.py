"""Chain node definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, ClassVar

from little_agent.types import ContentBlock, JSONValue


@dataclass(slots=True)
class Node:
    """Base chain node."""

    id: str
    prev: Node | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    kind: ClassVar[str] = "node"

    def to_dict(self) -> dict[str, JSONValue]:
        """Serialize node to dict."""
        return {"kind": self.kind, "id": self.id}

    @classmethod
    def from_dict(cls, data: dict[str, Any], prev: Node | None = None) -> Node:
        """Deserialize node from dict."""
        raise NotImplementedError


@dataclass(slots=True)
class UserPromptNode(Node):
    """User prompt node."""

    kind: ClassVar[str] = "user_prompt"
    prompt: str | list[ContentBlock] = ""

    def to_dict(self) -> dict[str, JSONValue]:
        base = Node.to_dict(self)
        base["prompt"] = self.prompt  # type: ignore[assignment]
        return base

    @classmethod
    def from_dict(cls, data: dict[str, Any], prev: Node | None = None) -> Node:
        prompt = data.get("prompt", "")
        if not isinstance(prompt, (str, list)):
            raise ValueError("UserPromptNode 'prompt' must be a string or list")
        return cls(id=data["id"], prev=prev, prompt=prompt)


@dataclass(slots=True)
class AssistantResponseNode(Node):
    """Assistant response node."""

    kind: ClassVar[str] = "assistant_response"
    text: str = ""
    frozen: bool = False

    def to_dict(self) -> dict[str, JSONValue]:
        base = Node.to_dict(self)
        base["text"] = self.text
        return base

    @classmethod
    def from_dict(cls, data: dict[str, Any], prev: Node | None = None) -> Node:
        text = data.get("text", "")
        if not isinstance(text, str):
            raise ValueError("AssistantResponseNode 'text' must be a string")
        return cls(id=data["id"], prev=prev, text=text, frozen=True)


@dataclass(slots=True)
class ToolCallNode(Node):
    """Tool call node."""

    kind: ClassVar[str] = "tool_call"
    calls: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        base = Node.to_dict(self)
        base["calls"] = self.calls  # type: ignore[assignment]
        return base

    @classmethod
    def from_dict(cls, data: dict[str, Any], prev: Node | None = None) -> Node:
        calls = data.get("calls", {})
        if not isinstance(calls, dict):
            raise ValueError("ToolCallNode 'calls' must be a dict")
        return cls(id=data["id"], prev=prev, calls=calls)


@dataclass(slots=True)
class ToolResultNode(Node):
    """Tool result node."""

    kind: ClassVar[str] = "tool_result"
    results: dict[str, dict[str, Any]] = field(default_factory=dict)
    frozen: bool = False

    def to_dict(self) -> dict[str, JSONValue]:
        base = Node.to_dict(self)
        base["results"] = self.results  # type: ignore[assignment]
        return base

    @classmethod
    def from_dict(cls, data: dict[str, Any], prev: Node | None = None) -> Node:
        results = data.get("results", {})
        if not isinstance(results, dict):
            raise ValueError("ToolResultNode 'results' must be a dict")
        return cls(id=data["id"], prev=prev, results=results, frozen=True)


@dataclass(slots=True)
class SummaryNode(Node):
    """Summary node."""

    kind: ClassVar[str] = "summary"
    summary: JSONValue = None

    def to_dict(self) -> dict[str, JSONValue]:
        base = Node.to_dict(self)
        base["summary"] = self.summary
        return base

    @classmethod
    def from_dict(cls, data: dict[str, Any], prev: Node | None = None) -> Node:
        return cls(id=data["id"], prev=prev, summary=data.get("summary"))


_NODE_REGISTRY: dict[str, type[Node]] = {
    UserPromptNode.kind: UserPromptNode,
    AssistantResponseNode.kind: AssistantResponseNode,
    ToolCallNode.kind: ToolCallNode,
    ToolResultNode.kind: ToolResultNode,
    SummaryNode.kind: SummaryNode,
}


def _rebuild_chain(chain: list[Any]) -> Node | None:
    """Rebuild node chain from serialized data."""
    if not chain:
        return None
    prev: Node | None = None
    for item in chain:
        prev = _rebuild_node(item, prev)
    return prev


def _rebuild_node(item: Any, prev: Node | None) -> Node:
    """Rebuild a single node from serialized data."""
    if not isinstance(item, dict):
        raise ValueError("Chain item must be a dict")
    kind = item.get("kind")
    node_id = item.get("id")
    if not isinstance(kind, str) or not isinstance(node_id, str):
        raise ValueError("Chain item must have 'kind' and 'id' as strings")
    node_cls = _NODE_REGISTRY.get(kind)
    if node_cls is None:
        raise ValueError(f"Unknown node kind: {kind}")
    return node_cls.from_dict(item, prev)
