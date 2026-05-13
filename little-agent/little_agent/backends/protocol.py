"""Backend protocol definitions."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Protocol

from little_agent.types import Node, SessionUpdate

if TYPE_CHECKING:
    from little_agent.tools.protocol import ToolMap


@dataclass
class BackendToolCall:
    """Represents a tool call from the backend."""

    call_id: str
    tool_name: str
    arguments: dict[str, Any]
    error: str | None = None


@dataclass
class BackendTurnResult:
    """Represents the result of a single backend turn."""

    output_text: str
    tool_calls: list[BackendToolCall]
    finish_reason: Literal["completed", "tool_call"]
    usage: dict[str, int] | None = None
    thinking_text: str | None = None


class BackendSession(Protocol):
    """Minimal session contract required by Backend.generate()."""

    id: str
    system_prompt: str | None
    summaries: list[str]
    messages: list[Node]

    def get_turn_tool_map(self) -> "ToolMap": ...


class Backend(Protocol):
    """Backend protocol for LLM providers."""

    context_window: int

    def generate(
        self, session: BackendSession
    ) -> AsyncIterator[SessionUpdate | BackendTurnResult]: ...
