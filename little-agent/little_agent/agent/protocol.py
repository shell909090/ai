"""Agent protocol definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

from little_agent.tools.protocol import AsyncToolFn, ToolMap, ToolProvider
from little_agent.types import ContentBlock, JSONValue

if TYPE_CHECKING:
    from .hooks import Hook
    from .nodes import Node


StopReason = Literal["end_turn", "cancelled"]
PromptReturn = tuple[StopReason, str]


@dataclass
class SessionUpdate:
    """Event from agent (and producing backends) to client."""

    type: Literal[
        "agent_message_chunk",
        "thinking_chunk",
        "tool_call",
        "tool_call_update",
    ]
    data: dict[str, JSONValue]


class ToolRegistry(Protocol):
    """Agent-facing interface: register providers, describe tools, get callables."""

    def register(self, provider: ToolProvider) -> None: ...

    def desc_tool(
        self,
        names: set[str] | None = None,
        *,
        exclude: set[str] | None = None,
    ) -> ToolMap: ...

    def __getitem__(self, name: str) -> AsyncToolFn:
        """Return callable for a named tool; raise KeyError if not found."""
        ...


class Client(Protocol):
    """Frontend-facing contract: receives session updates and answers permission prompts."""

    async def update(self, session: Session, update: SessionUpdate) -> None: ...

    async def request_permission(
        self,
        session: Session,
        kind: str,
        payload: dict[str, JSONValue],
    ) -> bool: ...


class PermissionChecker(Protocol):
    """Protocol for permission checkers in the Chain of Responsibility."""

    async def request_permission(
        self,
        session: Session,
        kind: str,
        payload: dict[str, JSONValue],
    ) -> bool: ...


class Compressor(Protocol):
    """Compressor protocol."""

    async def compress(self, head: Node | None) -> Node | None: ...


class Session(Protocol):
    """Session protocol."""

    id: str
    cwd: str | None
    tail: object  # Node | None; kept as object to avoid importing Node at runtime

    async def prompt(
        self, prompt: str | list[ContentBlock], allowed_tools: list[str] | None = None
    ) -> PromptReturn: ...

    async def cancel(self) -> None: ...

    async def fork(self) -> Session: ...

    async def compress(self) -> None: ...

    def save(self) -> JSONValue: ...


class Agent(Protocol):
    """Agent protocol."""

    tools: ToolRegistry
    hooks: list[Hook]

    def __init__(self, *args: object, **kwargs: object) -> None: ...

    async def new(self, cwd: str | None = None) -> Session: ...

    async def load(self, data: JSONValue) -> Session: ...
