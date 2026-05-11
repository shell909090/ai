"""Chain node definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, ClassVar

from little_agent.types import ContentBlock, JSONValue


def _parse_created_at(value: Any) -> datetime:
    """Parse ISO datetime string; fall back to now(UTC) if absent or invalid."""
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    return datetime.now(UTC)


@dataclass(slots=True)
class Node:
    """Base chain node."""

    id: str
    prev: Node | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    kind: ClassVar[str] = "node"

    def to_dict(self) -> dict[str, JSONValue]:
        """Serialize node to dict."""
        return {"kind": self.kind, "id": self.id, "created_at": self.created_at.isoformat()}

    def freeze(self) -> None:
        """Freeze this node (no-op for nodes without mutable state)."""

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
        return cls(
            id=data["id"],
            prev=prev,
            prompt=prompt,
            created_at=_parse_created_at(data.get("created_at")),
        )


@dataclass(slots=True)
class AssistantResponseNode(Node):
    """Assistant response node."""

    kind: ClassVar[str] = "assistant_response"
    text: str = ""
    thinking: str = ""
    frozen: bool = False

    def freeze(self) -> None:
        """Mark this node as frozen, preventing further text appends."""
        self.frozen = True

    def to_dict(self) -> dict[str, JSONValue]:
        base = Node.to_dict(self)
        base["text"] = self.text
        if self.thinking:
            base["thinking"] = self.thinking
        return base

    @classmethod
    def from_dict(cls, data: dict[str, Any], prev: Node | None = None) -> Node:
        text = data.get("text", "")
        if not isinstance(text, str):
            raise ValueError("AssistantResponseNode 'text' must be a string")
        thinking = str(data.get("thinking") or "")
        return cls(
            id=data["id"],
            prev=prev,
            text=text,
            thinking=thinking,
            frozen=True,
            created_at=_parse_created_at(data.get("created_at")),
        )


@dataclass(slots=True)
class ToolCallNode(Node):
    """Tool call node."""

    kind: ClassVar[str] = "tool_call"
    output_text: str = ""
    thinking: str = ""
    calls: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        base = Node.to_dict(self)
        base["output_text"] = self.output_text
        if self.thinking:
            base["thinking"] = self.thinking
        base["calls"] = self.calls  # type: ignore[assignment]
        return base

    @classmethod
    def from_dict(cls, data: dict[str, Any], prev: Node | None = None) -> Node:
        output_text = str(data.get("output_text") or "")
        thinking = str(data.get("thinking") or "")
        calls = data.get("calls", {})
        if not isinstance(calls, dict):
            raise ValueError("ToolCallNode 'calls' must be a dict")
        return cls(
            id=data["id"],
            prev=prev,
            output_text=output_text,
            thinking=thinking,
            calls=calls,
            created_at=_parse_created_at(data.get("created_at")),
        )


@dataclass(slots=True)
class ToolResultNode(Node):
    """Tool result node."""

    kind: ClassVar[str] = "tool_result"
    results: dict[str, dict[str, Any]] = field(default_factory=dict)
    frozen: bool = False

    def freeze(self) -> None:
        """Mark this node as frozen, preventing further result additions."""
        self.frozen = True

    def to_dict(self) -> dict[str, JSONValue]:
        base = Node.to_dict(self)
        base["results"] = self.results  # type: ignore[assignment]
        return base

    @classmethod
    def from_dict(cls, data: dict[str, Any], prev: Node | None = None) -> Node:
        results = data.get("results", {})
        if not isinstance(results, dict):
            raise ValueError("ToolResultNode 'results' must be a dict")
        return cls(
            id=data["id"],
            prev=prev,
            results=results,
            frozen=True,
            created_at=_parse_created_at(data.get("created_at")),
        )


@dataclass(slots=True)
class SummaryNode(Node):
    """Summary node."""

    kind: ClassVar[str] = "summary"
    summary: str = ""

    def to_dict(self) -> dict[str, JSONValue]:
        base = Node.to_dict(self)
        base["summary"] = self.summary
        return base

    @classmethod
    def from_dict(cls, data: dict[str, Any], prev: Node | None = None) -> Node:
        return cls(
            id=data["id"],
            prev=prev,
            summary=str(data.get("summary") or ""),
            created_at=_parse_created_at(data.get("created_at")),
        )


_NODE_REGISTRY: dict[str, type[Node]] = {
    UserPromptNode.kind: UserPromptNode,
    AssistantResponseNode.kind: AssistantResponseNode,
    ToolCallNode.kind: ToolCallNode,
    ToolResultNode.kind: ToolResultNode,
    SummaryNode.kind: SummaryNode,
}

_KIND_REQUIRED_FIELDS: dict[str, dict[str, type]] = {
    "user_prompt": {"id": str, "kind": str},
    "assistant_response": {"id": str, "kind": str, "text": str},
    "tool_call": {"id": str, "kind": str, "calls": dict},
    "tool_result": {"id": str, "kind": str, "results": dict},
    "summary": {"id": str, "kind": str, "summary": str},
}


def validate_node_dict(d: dict[str, Any]) -> None:
    """Validate a serialized node dict; raises ValueError on any violation."""
    if not isinstance(d, dict):
        raise ValueError(f"invalid session data: node must be a dict, got {type(d).__name__}")
    node_id = d.get("id")
    if not isinstance(node_id, str) or not node_id:
        raise ValueError("invalid session data: node missing required 'id' string field")
    kind = d.get("kind")
    if not isinstance(kind, str) or not kind:
        raise ValueError("invalid session data: node missing required 'kind' string field")
    if kind not in _NODE_REGISTRY:
        raise ValueError(f"invalid session data: unknown node kind {kind!r}")
    required = _KIND_REQUIRED_FIELDS.get(kind, {})
    for fname, expected_type in required.items():
        val = d.get(fname)
        # Allow optional fields that may be absent (only validate when present).
        if val is not None and not isinstance(val, expected_type):
            raise ValueError(
                f"invalid session data: {kind}.{fname} must be {expected_type.__name__}, "
                f"got {type(val).__name__}"
            )


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
