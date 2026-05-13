"""Session context variables for structured logging."""

from __future__ import annotations

import contextvars

# Injected into every log record via _ContextFilter when set.
current_session_id: contextvars.ContextVar[str] = contextvars.ContextVar("session_id", default="-")
current_turn_id: contextvars.ContextVar[str] = contextvars.ContextVar("turn_id", default="-")
