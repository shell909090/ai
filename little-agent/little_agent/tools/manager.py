"""Tool manager implementation."""

from little_agent.types import JSONValue

from .exceptions import ToolInvokeError
from .protocol import ToolManager as ToolManagerProtocol
from .protocol import ToolMap, ToolProvider


class AggregatedToolManager(ToolManagerProtocol):
    """Aggregates multiple tool providers."""

    def __init__(self) -> None:
        self._providers: list[ToolProvider] = []
        self._tools: ToolMap = {}

    def register(self, provider: ToolProvider) -> None:
        """Register a tool provider."""
        self._providers.append(provider)
        self._tools.update(provider.list())

    def list(self) -> ToolMap:
        """Return all registered tools."""
        return self._tools.copy()

    async def invoke(self, name: str, **kwargs: JSONValue) -> JSONValue:
        """Invoke a tool by name."""
        for provider in self._providers:
            if name in provider.list():
                return await provider.invoke(name, **kwargs)
        raise ToolInvokeError(f"Tool '{name}' not found")
