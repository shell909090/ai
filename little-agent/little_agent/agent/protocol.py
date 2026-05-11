"""Agent protocol definitions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from little_agent.types import ContentBlock, JSONValue, PromptReturn

if TYPE_CHECKING:
    from little_agent.tools.protocol import ToolRegistry

    from .nodes import Node


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
    hooks: list[object]

    def __init__(self, *args: object, **kwargs: object) -> None: ...

    async def new(self, cwd: str | None = None) -> Session: ...

    async def load(self, data: JSONValue) -> Session: ...
