"""AgentCore: shared configuration and session factory."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, cast

from little_agent.types import JSONValue

from .hooks import Hook
from .nodes import validate_node_dict
from .protocol import Agent, Compressor, PermissionChecker, Session
from .session import SessionCore

if TYPE_CHECKING:
    from little_agent.backends.protocol import Backend
    from little_agent.frontends.protocol import Client
    from little_agent.tools.protocol import ToolRegistry


def _validate_chain(chain: list[Any]) -> None:
    """Pre-validate all chain items; check schema and ID uniqueness."""
    seen_ids: set[str] = set()
    for i, item in enumerate(chain):
        if not isinstance(item, dict):
            raise ValueError(f"invalid session data: chain item {i} must be a dict")
        try:
            validate_node_dict(item)
        except ValueError as exc:
            raise ValueError(f"invalid session data: chain item {i}: {exc}") from exc
        node_id: str = item["id"]
        if node_id in seen_ids:
            raise ValueError(f"invalid session data: duplicate node id {node_id!r} at position {i}")
        seen_ids.add(node_id)


class AgentCore(Agent):
    def __init__(
        self,
        client: Client,
        backend: Backend,
        tools: ToolRegistry,
        compressor: Compressor | None = None,
        permissions: PermissionChecker | None = None,
        hooks: list[Hook] | None = None,
        compress_ratio: float = 0.75,
        context_window: int = 128000,
    ) -> None:
        self.client = client
        self.backend = backend
        self.tools = tools
        self.compressor = compressor
        self.permissions: PermissionChecker = (
            permissions if permissions is not None else cast(PermissionChecker, client)
        )
        self.hooks: list[Hook] = hooks or []  # type: ignore[assignment]
        self.compress_ratio = compress_ratio
        self.context_window = context_window

    async def new(self, cwd: str | None = None) -> Session:
        """Create a new session."""
        return SessionCore(
            session_id=str(uuid.uuid4()),
            cwd=cwd,
            agent=self,
        )

    async def load(self, data: JSONValue) -> Session:
        """Load a session from serialized data."""
        if not isinstance(data, dict):
            raise ValueError("Invalid session data: expected dict")
        session_id = data.get("id")
        if not isinstance(session_id, str):
            raise ValueError("Session data missing 'id'")
        session_cwd = data.get("cwd")
        if session_cwd is not None and not isinstance(session_cwd, str):
            raise ValueError("Session 'cwd' must be a string or null")
        session = SessionCore(
            session_id=session_id,
            cwd=session_cwd,
            agent=self,
        )
        chain = data.get("chain", [])
        if isinstance(chain, list):
            _validate_chain(chain)
            session._rebuild_tail(chain)
        return session
