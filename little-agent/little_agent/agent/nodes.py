"""Chain node definitions."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, ClassVar

from little_agent.types import ContentBlock, JSONValue, Node


def _format_result(result: dict[str, Any]) -> str:
    """Format a tool result dict as multi-line k: v text for backend messages."""
    lines = []
    for k, v in result.items():
        if isinstance(v, str):
            lines.append(f"{k}: {v}")
        else:
            try:
                lines.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
            except (TypeError, ValueError):
                lines.append(f"{k}: {v!s}")
    return "\n".join(lines)


def _parse_created_at(value: Any) -> datetime:
    """Parse ISO datetime string; fall back to now(UTC) if absent or invalid."""
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    return datetime.now(UTC)


@dataclass(slots=True)
class UserPromptNode:
    """User prompt node."""

    kind: ClassVar[str] = "user_prompt"
    id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    prompt: str | list[ContentBlock] = ""

    def to_dict(self) -> dict[str, JSONValue]:
        """Serialize node to dict."""
        return {
            "kind": self.kind,
            "id": self.id,
            "created_at": self.created_at.isoformat(),
            "prompt": self.prompt,  # type: ignore[dict-item]
        }

    def to_anthropic(self) -> list[dict[str, Any]]:
        """Convert to Anthropic user message."""
        return [{"role": "user", "content": self.prompt}]

    def to_openai(self) -> list[dict[str, Any]]:
        """Convert to OpenAI user message."""
        return [{"role": "user", "content": self.prompt}]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UserPromptNode:
        """Deserialize from dict."""
        prompt = data.get("prompt", "")
        if not isinstance(prompt, (str, list)):
            raise ValueError("UserPromptNode 'prompt' must be a string or list")
        return cls(
            id=data["id"],
            prompt=prompt,
            created_at=_parse_created_at(data.get("created_at")),
        )


@dataclass(slots=True)
class AssistantNode:
    """Assistant message node (text reply or tool call)."""

    kind: ClassVar[str] = "assistant"
    id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    text: str = ""
    thinking: str = ""
    tool_calls: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        """Serialize node to dict."""
        d: dict[str, JSONValue] = {
            "kind": self.kind,
            "id": self.id,
            "created_at": self.created_at.isoformat(),
            "text": self.text,
        }
        if self.thinking:
            d["thinking"] = self.thinking
        if self.tool_calls:
            d["tool_calls"] = self.tool_calls  # type: ignore[assignment]
        return d

    def to_anthropic(self) -> list[dict[str, Any]]:
        """Convert to Anthropic assistant message."""
        if not self.tool_calls:
            return [{"role": "assistant", "content": [{"type": "text", "text": self.text}]}]
        content_blocks: list[dict[str, Any]] = []
        if self.text:
            content_blocks.append({"type": "text", "text": self.text})
        content_blocks.extend(
            {
                "type": "tool_use",
                "id": call_id,
                "name": call_data["tool_name"],
                "input": call_data["arguments"],
            }
            for call_id, call_data in self.tool_calls.items()
        )
        return [{"role": "assistant", "content": content_blocks}]

    def to_openai(self) -> list[dict[str, Any]]:
        """Convert to OpenAI assistant message."""
        if not self.tool_calls:
            return [{"role": "assistant", "content": self.text}]
        tool_calls = [
            {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": call_data["tool_name"],
                    "arguments": json.dumps(call_data["arguments"]),
                },
            }
            for call_id, call_data in self.tool_calls.items()
        ]
        msg: dict[str, Any] = {"role": "assistant", "tool_calls": tool_calls}
        if self.text:
            msg["content"] = self.text
        return [msg]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AssistantNode:
        """Deserialize from dict."""
        text = str(data.get("text") or "")
        thinking = str(data.get("thinking") or "")
        tool_calls = data.get("tool_calls", {})
        if not isinstance(tool_calls, dict):
            raise ValueError("AssistantNode 'tool_calls' must be a dict")
        return cls(
            id=data["id"],
            text=text,
            thinking=thinking,
            tool_calls=tool_calls,
            created_at=_parse_created_at(data.get("created_at")),
        )


@dataclass(slots=True)
class ToolResultNode:
    """Tool result node."""

    kind: ClassVar[str] = "tool_result"
    id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    results: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        """Serialize node to dict."""
        return {
            "kind": self.kind,
            "id": self.id,
            "created_at": self.created_at.isoformat(),
            "results": self.results,  # type: ignore[dict-item]
        }

    def to_anthropic(self) -> list[dict[str, Any]]:
        """Convert to Anthropic user message with tool_result blocks."""
        return [
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": call_id,
                        "content": _format_result(result),
                    }
                    for call_id, result in self.results.items()
                ],
            }
        ]

    def to_openai(self) -> list[dict[str, Any]]:
        """Convert to one OpenAI tool message per result."""
        return [
            {
                "role": "tool",
                "tool_call_id": call_id,
                "content": _format_result(result),
            }
            for call_id, result in self.results.items()
        ]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToolResultNode:
        """Deserialize from dict."""
        results = data.get("results", {})
        if not isinstance(results, dict):
            raise ValueError("ToolResultNode 'results' must be a dict")
        return cls(
            id=data["id"],
            results=results,
            created_at=_parse_created_at(data.get("created_at")),
        )


_NODE_REGISTRY: dict[str, Any] = {
    UserPromptNode.kind: UserPromptNode,
    AssistantNode.kind: AssistantNode,
    ToolResultNode.kind: ToolResultNode,
}

_KIND_REQUIRED_FIELDS: dict[str, dict[str, type]] = {
    "user_prompt": {"id": str, "kind": str},
    "assistant": {"id": str, "kind": str, "tool_calls": dict},
    "tool_result": {"id": str, "kind": str, "results": dict},
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
        if val is not None and not isinstance(val, expected_type):
            raise ValueError(
                f"invalid session data: {kind}.{fname} must be {expected_type.__name__}, "
                f"got {type(val).__name__}"
            )


def _parse_messages(data_list: list[Any]) -> list[Node]:
    """Parse a list of serialized node dicts into Node objects (chronological order)."""
    nodes: list[Node] = []
    for i, item in enumerate(data_list):
        if not isinstance(item, dict):
            raise ValueError(f"Message item {i} must be a dict")
        kind = item.get("kind")
        node_cls = _NODE_REGISTRY.get(kind)  # type: ignore[arg-type]
        if node_cls is None:
            raise ValueError(f"Unknown node kind: {kind!r}")
        nodes.append(node_cls.from_dict(item))
    return nodes
