"""Session context variable for tool invocation."""

from __future__ import annotations

import contextvars
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_agent.agent.session import SessionCore

current_session: contextvars.ContextVar["SessionCore | None"] = contextvars.ContextVar(
    "current_session", default=None
)
