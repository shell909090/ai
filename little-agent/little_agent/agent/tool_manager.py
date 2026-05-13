"""ToolManager: default ToolRegistry implementation."""

from __future__ import annotations

from little_agent.tools.protocol import AsyncToolFn, ToolDef, ToolMap, ToolProvider


class ToolManager:
    """Implements ToolRegistry: aggregates ToolProviders."""

    def __init__(self) -> None:
        self._registry: dict[str, tuple[ToolDef, AsyncToolFn]] = {}

    def register(self, provider: ToolProvider) -> None:
        """Register all tools from a provider; raises ValueError on name conflict."""
        for name, tooldef, fn in provider:
            if name in self._registry:
                raise ValueError(f"Tool '{name}' already registered")
            self._registry[name] = (tooldef, fn)

    def desc_tool(
        self,
        names: set[str] | None = None,
        *,
        exclude: set[str] | None = None,
    ) -> ToolMap:
        """Return ToolMap for the given name set, minus any excluded names."""
        result = (
            {n: td for n, (td, _) in self._registry.items()}
            if names is None
            else {n: td for n, (td, _) in self._registry.items() if n in names}
        )
        if exclude:
            result = {n: td for n, td in result.items() if n not in exclude}
        return result

    def __getitem__(self, name: str) -> AsyncToolFn:
        """Return the callable for a tool; raises KeyError if not found."""
        if name not in self._registry:
            raise KeyError(f"Tool '{name}' not found")
        return self._registry[name][1]
