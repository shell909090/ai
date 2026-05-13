"""Shared types: JSON primitives and cross-package contracts.

This module is intentionally a leaf at runtime: nothing in this file
imports any other little_agent module at runtime. TYPE_CHECKING-only
imports of tools.protocol types are used so ToolRegistry's method
signatures stay precise without dragging the tools layer into runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from little_agent.tools.protocol import AsyncToolFn, ToolMap, ToolProvider


JSONScalar = str | int | float | bool | None
JSONValue = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
ContentBlock = dict[str, JSONValue]

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


class Hook:
    """Lifecycle hook base class. Override only the events you care about.

    Hook callbacks deliberately do NOT receive a node parameter: when each
    callback fires, ``session.tail`` points at the just-frozen node the
    callback would have been told about. Implementations that need the node
    read ``session.tail`` (and ``session.tail.prev`` if they want neighbours).
    """

    async def on_turn_start(self, session: Session) -> None:
        """Called before UserPromptNode is appended."""

    async def on_turn_end(self, session: Session) -> None:
        """Called in finally after turn completes, is cancelled, or raises."""

    async def on_tool_call(self, session: Session) -> None:
        """Called after ToolCallNode is appended and frozen; session.tail is that node."""

    async def on_tool_result(self, session: Session) -> None:
        """Called after ToolResultNode is frozen; session.tail is that node."""

    async def on_compress(self, session: Session) -> None:
        """Called after compress task completes."""

    async def on_fork(self, source: Session, forked: Session) -> None:
        """Called after fork() creates a new session."""

    async def on_cancel(self, session: Session) -> None:
        """Called after turn is cancelled and unfinalised nodes are frozen."""


class Agent(Protocol):
    """Agent protocol."""

    tools: ToolRegistry
    hooks: list[Hook]

    def __init__(self, *args: object, **kwargs: object) -> None: ...

    async def new(self, cwd: str | None = None) -> Session: ...

    async def load(self, data: JSONValue) -> Session: ...
