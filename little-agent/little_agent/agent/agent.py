"""AgentCore: shared configuration and session factory."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from little_agent.types import (
    Agent,
    Client,
    Compressor,
    Hook,
    JSONValue,
    PermissionChecker,
    Session,
    ToolRegistry,
)

from .nodes import _parse_messages, validate_node_dict
from .session import SessionCore

if TYPE_CHECKING:
    from little_agent.backends.protocol import Backend


def _find_agents_md(cwd: str | None) -> str | None:
    """Search for AGENTS.md from cwd upward, then ~/.config/AGENTS.md."""
    start = Path(cwd).resolve() if cwd else Path.cwd()
    current = start
    while True:
        candidate = current / "AGENTS.md"
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
        parent = current.parent
        if parent == current:
            break
        current = parent
    fallback = Path.home() / ".config" / "AGENTS.md"
    if fallback.is_file():
        return fallback.read_text(encoding="utf-8")
    return None


def _validate_messages(messages: list[Any]) -> None:
    """Pre-validate all message items; check schema and ID uniqueness."""
    seen_ids: set[str] = set()
    for i, item in enumerate(messages):
        if not isinstance(item, dict):
            raise ValueError(f"invalid session data: message item {i} must be a dict")
        try:
            validate_node_dict(item)
        except ValueError as exc:
            raise ValueError(f"invalid session data: message item {i}: {exc}") from exc
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
        compress_threshold: float = 0.75,
        context_window: int = 128000,
        max_tool_result_chars: int = 50000,
        system_prompt: str | None = None,
        compressed_window_tokens: int = 0,
        ignore_agentsmd: bool = False,
    ) -> None:
        self.client = client
        self.backend = backend
        self.tools = tools
        self.compressor = compressor
        self.permissions: PermissionChecker = (
            permissions if permissions is not None else cast(PermissionChecker, client)
        )
        self.hooks: list[Hook] = hooks if hooks is not None else []
        self.compress_threshold = compress_threshold
        self.context_window = context_window
        self.max_tool_result_chars = max_tool_result_chars
        self.system_prompt = system_prompt
        self.compressed_window_tokens = compressed_window_tokens
        self.ignore_agentsmd = ignore_agentsmd

    async def new(self, cwd: str | None = None) -> Session:
        """Create a new session; load AGENTS.md into system_prompt and fire on_session_new."""
        session = SessionCore(session_id=str(uuid.uuid4()), cwd=cwd, agent=self)
        session.system_prompt = self.system_prompt
        if not self.ignore_agentsmd:
            agents_md = _find_agents_md(cwd)
            if agents_md:
                if session.system_prompt:
                    session.system_prompt = session.system_prompt + "\n\n" + agents_md
                else:
                    session.system_prompt = agents_md
        await session.call_hooks("on_session_new", session)
        return session

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
        session = SessionCore(session_id=session_id, cwd=session_cwd, agent=self)

        system_prompt = data.get("system_prompt")
        if system_prompt is not None and not isinstance(system_prompt, str):
            raise ValueError("Session 'system_prompt' must be a string or null")
        session.system_prompt = system_prompt

        summaries = data.get("summaries", [])
        if not isinstance(summaries, list) or not all(isinstance(s, str) for s in summaries):
            raise ValueError("Session 'summaries' must be a list of strings")
        session.summaries = [str(s) for s in summaries]

        messages_data = data.get("messages", [])
        if not isinstance(messages_data, list):
            raise ValueError("Session 'messages' must be a list")
        _validate_messages(messages_data)
        session.messages = _parse_messages(messages_data)
        return session
