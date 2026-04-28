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


@dataclass(slots=True)
class UserPromptNode(Node):
    """User prompt node."""

    kind: ClassVar[str] = "user_prompt"
    prompt: str | list[ContentBlock] = ""


@dataclass(slots=True)
class AssistantResponseNode(Node):
    """Assistant response node."""

    kind: ClassVar[str] = "assistant_response"
    text: str = ""
    frozen: bool = False


@dataclass(slots=True)
class ToolCallNode(Node):
    """Tool call node."""

    kind: ClassVar[str] = "tool_call"
    calls: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass(slots=True)
class ToolResultNode(Node):
    """Tool result node."""

    kind: ClassVar[str] = "tool_result"
    results: dict[str, dict[str, Any]] = field(default_factory=dict)
    frozen: bool = False


@dataclass(slots=True)
class SummaryNode(Node):
    """Summary node."""

    kind: ClassVar[str] = "summary"
    summary: JSONValue = None
