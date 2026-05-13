"""Agent-internal protocol definitions.

Cross-package contracts (Agent, Session, Client, PermissionChecker,
ToolRegistry, SessionUpdate, StopReason, PromptReturn) live in
``little_agent.types``. Only Compressor remains here because it accepts
and returns ``Node``, which is agent-internal.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from .nodes import Node


class Compressor(Protocol):
    """Compressor protocol."""

    async def compress(self, head: Node | None) -> Node | None: ...
