"""Tool protocol definitions."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from little_agent.types import JSONValue

ToolArgDef = tuple[str, str, str, bool]
ToolDef = tuple[str, list[ToolArgDef]]
ToolMap = dict[str, ToolDef]


@runtime_checkable
class ToolProvider(Protocol):
    """Tool provider protocol."""

    def list(self) -> ToolMap: ...

    async def invoke(self, name: str, **kwargs: JSONValue) -> JSONValue: ...
