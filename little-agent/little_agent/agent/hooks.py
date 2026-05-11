"""Hook base class for session lifecycle events."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_agent.agent.nodes import ToolCallNode, ToolResultNode
    from little_agent.agent.protocol import Session


class Hook:
    """Lifecycle hook. Override only the events you care about."""

    async def on_turn_start(self, session: "Session") -> None:
        """Called before UserPromptNode is appended."""

    async def on_turn_end(self, session: "Session") -> None:
        """Called in finally after turn completes, is cancelled, or raises."""

    async def on_tool_call(self, session: "Session", node: "ToolCallNode") -> None:
        """Called after ToolCallNode is frozen."""

    async def on_tool_result(self, session: "Session", node: "ToolResultNode") -> None:
        """Called after ToolResultNode results are all in and frozen."""

    async def on_compress(self, session: "Session") -> None:
        """Called after compress task completes."""

    async def on_fork(self, source: "Session", forked: "Session") -> None:
        """Called after fork() creates a new session."""

    async def on_cancel(self, session: "Session") -> None:
        """Called after turn is cancelled and unfinalised nodes are frozen."""
