"""Backend protocol definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Protocol

if TYPE_CHECKING:
    from little_agent.agent.core import SessionCore


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
    finish_reason: Literal["completed", "tool_call", "cancelled"]


class Backend(Protocol):
    """Backend protocol for LLM providers."""

    async def generate(self, session: SessionCore) -> BackendTurnResult: ...
