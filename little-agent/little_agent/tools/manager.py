"""Tool manager implementation."""

from typing import cast

from little_agent.types import JSONValue

from .exceptions import ToolInvokeError
from .protocol import ToolMap, ToolProvider

# Names reserved by the ToolProvider Protocol; never treated as tool methods.
_RESERVED = frozenset({"list", "invoke"})


class ToolManager:
    """Aggregates multiple tool providers."""

    def __init__(self) -> None:
        self._providers: list[ToolProvider] = []
        self._tools: ToolMap = {}
        self._index: dict[str, ToolProvider] = {}

    def register(self, provider: ToolProvider) -> None:
        """Register a tool provider."""
        self._providers.append(provider)
        for name in provider.list():
            self._index[name] = provider
        self._tools.update(provider.list())

    def list(self) -> ToolMap:
        """Return all registered tools."""
        return self._tools.copy()

    async def invoke(self, name: str, kwargs: dict[str, JSONValue]) -> JSONValue:
        """Invoke a tool by name.

        Fast path: if the provider exposes a method whose name matches the tool
        name (and the name is not a reserved Protocol method), call it directly,
        skipping the provider's own invoke() dispatch layer.
        """
        provider = self._index.get(name)
        if provider is None:
            raise ToolInvokeError(f"Tool '{name}' not found")
        if name not in _RESERVED:
            method = getattr(provider, name, None)
            if callable(method):
                return cast(JSONValue, await method(**kwargs))
        return await provider.invoke(name, kwargs)
