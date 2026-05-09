"""Shared logging helpers for backend streaming requests and responses."""

from __future__ import annotations

import logging
from typing import Any


def _log_streaming_request(
    logger: logging.Logger,
    name: str,
    model: str,
    messages: list[Any],
    tools: list[Any] | None,
) -> None:
    """Log a streaming request at DEBUG level."""
    logger.debug(
        "%s streaming request: model=%s messages=%s tools=%s",
        name,
        model,
        messages,
        tools,
    )


def _log_streaming_response(
    logger: logging.Logger,
    name: str,
    model: str,
    finish_reason: str,
    usage: dict[str, int] | None,
    elapsed: float,
) -> None:
    """Log a streaming response at INFO level."""
    logger.info(
        "%s streaming response: model=%s finish_reason=%s "
        "input_tokens=%s cached_tokens=%s output_tokens=%s elapsed=%.3fs",
        name,
        model,
        finish_reason,
        usage.get("input_tokens") if usage else None,
        usage.get("cached_tokens") if usage else None,
        usage.get("output_tokens") if usage else None,
        elapsed,
    )
