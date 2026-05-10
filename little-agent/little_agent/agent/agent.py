"""AgentCore: shared configuration and session factory."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, cast

from little_agent.types import JSONValue

from .nodes import _NODE_REGISTRY
from .protocol import Agent, Compressor, PermissionChecker, Session
from .session import SessionCore

if TYPE_CHECKING:
    from little_agent.backends.protocol import Backend
    from little_agent.frontends.protocol import Client
    from little_agent.tools.protocol import ToolRegistry


def _validate_chain(chain: list[Any]) -> None:
    """Pre-validate all chain items before rebuilding; raises ValueError on the first bad node."""
    for i, item in enumerate(chain):
        if not isinstance(item, dict):
            raise ValueError(f"Chain item {i} must be a dict, got {type(item).__name__}")
        kind = item.get("kind")
        node_id = item.get("id")
        if not isinstance(kind, str):
            raise ValueError(f"Chain item {i} missing 'kind' string field")
        if not isinstance(node_id, str):
            raise ValueError(f"Chain item {i} missing 'id' string field")
        if kind not in _NODE_REGISTRY:
            raise ValueError(f"Chain item {i} has unknown kind: {kind!r}")


class AgentCore(Agent):
    def __init__(
        self,
        client: Client,
        backend: Backend,
        tools: ToolRegistry,
        compressor: Compressor | None = None,
        permissions: PermissionChecker | None = None,
        memory: Any = None,
        loggers: list[Any] | None = None,
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
        self.memory = memory
        self.loggers: list[Any] = loggers or []
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
