"""Session context variables for tool invocation and structured logging."""

from __future__ import annotations

import contextvars
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_agent.agent.session import SessionCore

current_session: contextvars.ContextVar["SessionCore | None"] = contextvars.ContextVar(
    "current_session", default=None
)

# Injected into every log record via _ContextFilter when set.
current_session_id: contextvars.ContextVar[str] = contextvars.ContextVar("session_id", default="-")
current_turn_id: contextvars.ContextVar[str] = contextvars.ContextVar("turn_id", default="-")
