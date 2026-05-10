"""Backend protocol definitions."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Protocol

from little_agent.types import SessionUpdate

if TYPE_CHECKING:
    from little_agent.agent.session import SessionCore


@dataclass
class BackendToolCall:
    """Represents a tool call from the backend."""

    call_id: str
    tool_name: str
    arguments: dict[str, Any]


@dataclass
class BackendTurnResult:
    """Represents the result of a single backend turn."""

    output_text: str
    tool_calls: list[BackendToolCall]
    finish_reason: Literal["completed", "tool_call"]
    usage: dict[str, int] | None = None
    thinking_text: str | None = None


class Backend(Protocol):
    """Backend protocol for LLM providers."""

    context_window: int

    def generate(
        self, session: SessionCore
    ) -> AsyncIterator[SessionUpdate | BackendTurnResult]: ...
