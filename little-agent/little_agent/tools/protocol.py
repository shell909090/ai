"""Tool protocol definitions."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from little_agent.types import JSONValue

AsyncToolFn = Callable[[dict[str, JSONValue]], Awaitable[JSONValue]]


@dataclass
class ToolArgDef:
    name: str  # parameter name
    type: str  # JSON Schema type, e.g. "string", "object", "integer"
    desc: str  # parameter description sent to the LLM
    required: bool = False


@dataclass
class ToolDef:
    desc: str  # tool description sent to the LLM
    args: list[ToolArgDef] = field(default_factory=list)


ToolMap = dict[str, ToolDef]


@runtime_checkable
class ToolProvider(Protocol):
    """Yields (name, tooldef, fn) triples for registration."""

    def __iter__(self) -> Iterator[tuple[str, ToolDef, AsyncToolFn]]:
        """Yield (name, tooldef, fn) triples."""
        ...
