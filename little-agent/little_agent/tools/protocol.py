"""Tool protocol definitions."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from little_agent.types import JSONValue

AsyncToolFn = Callable[[dict[str, JSONValue]], Awaitable[JSONValue]]


@dataclass
class ToolArgDef:
    name: str  # 参数名
    type: str  # JSON Schema 类型，如 "string"、"object"、"integer"
    desc: str  # 参数描述，传给 LLM
    required: bool = False


@dataclass
class ToolDef:
    desc: str  # 工具描述，传给 LLM
    args: list[ToolArgDef] = field(default_factory=list)


ToolMap = dict[str, ToolDef]


@runtime_checkable
class ToolProvider(Protocol):
    """Yields (name, tooldef, fn) triples for registration."""

    def __iter__(self) -> Iterator[tuple[str, ToolDef, AsyncToolFn]]:
        """Yield (name, tooldef, fn) triples."""
        ...


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
