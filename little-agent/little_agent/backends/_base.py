"""Shared base class for streaming LLM backends."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, NoReturn

from little_agent.types import SessionUpdate

from ._utils import _is_context_overflow
from .exceptions import (
    BackendError,
    BackendRateLimitError,
    BackendTimeoutError,
    ContextOverflowError,
)
from .protocol import BackendTurnResult

if TYPE_CHECKING:
    from little_agent.agent.session import SessionCore

logger = logging.getLogger(__name__)


@dataclass
class _StreamAccumulator:
    """Per-stream mutable state shared between streaming backends."""

    text: list[str] = field(default_factory=list)
    thinking: list[str] = field(default_factory=list)
    tool_blocks: dict[int, dict[str, Any]] = field(default_factory=dict)
    usage: dict[str, int] | None = None
    finish_reason_raw: str = ""

    def output_text(self) -> str:
        """Return accumulated visible text as a single string."""
        return "".join(self.text)

    def thinking_text(self) -> str | None:
        """Return accumulated thinking text, or None if empty."""
        return "".join(self.thinking) or None


class _StreamingBackend:
    """Common skeleton for streaming LLM backends.

    Provides shared ``__init__``, ``generate()``, and SDK error mapping.
    Subclasses implement ``_stream(session)``.
    """

    def __init__(
        self,
        model: str,
        timeout: float = 60.0,
        max_concurrency: int = 1,
        context_window: int = 128000,
    ) -> None:
        self._model = model
        self._timeout = timeout
        self._sem = asyncio.Semaphore(max_concurrency)
        self.context_window = context_window

    def generate(self, session: "SessionCore") -> AsyncIterator[SessionUpdate | BackendTurnResult]:
        """Return async iterator streaming the backend response."""
        return self._stream(session)

    def _stream(self, session: "SessionCore") -> AsyncIterator[SessionUpdate | BackendTurnResult]:
        """Subclass hook for the streaming loop."""
        raise NotImplementedError

    def _raise_mapped(
        self,
        e: BaseException,
        sdk_module: Any,
        overflow_substrings: tuple[str, ...],
        code: str | None = None,
    ) -> NoReturn:
        """Map a SDK / runtime exception to a project exception and re-raise."""
        if isinstance(e, TimeoutError):
            raise BackendTimeoutError(f"Backend API call timed out after {self._timeout}s") from e
        if isinstance(e, sdk_module.BadRequestError):
            if _is_context_overflow(e, overflow_substrings, code):
                raise ContextOverflowError(str(e)) from e
            raise BackendError(str(e)) from e
        if isinstance(e, sdk_module.RateLimitError):
            raise BackendRateLimitError(str(e)) from e
        if isinstance(e, sdk_module.APIError):
            raise BackendError(str(e)) from e
        raise e
