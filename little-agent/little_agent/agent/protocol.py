"""Agent protocol definitions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from little_agent.types import ContentBlock, JSONValue, PromptReturn

if TYPE_CHECKING:
    from little_agent.backends.protocol import Backend
    from little_agent.frontends.protocol import Client
    from little_agent.tools.protocol import ToolManager

    from .nodes import Node


class Compressor(Protocol):
    """Compressor protocol."""

    async def compress(self, head: Node | None) -> Node | None: ...


class Session(Protocol):
    """Session protocol."""

    async def prompt(self, prompt: str | list[ContentBlock]) -> PromptReturn: ...

    async def cancel(self) -> None: ...

    async def fork(self) -> Session: ...

    async def compress(self) -> None: ...

    def save(self) -> JSONValue: ...


class Agent(Protocol):
    """Agent protocol."""

    def __init__(
        self,
        client: Client,
        backend: Backend,
        tools: ToolManager,
        compressor: Compressor | None = None,
    ) -> None: ...

    async def new(self, cwd: str | None = None) -> Session: ...

    async def load(self, data: JSONValue) -> Session: ...
