"""Shared helpers for backend implementations."""

from __future__ import annotations

import copy
import json
import logging
from typing import Any

from little_agent.tools.protocol import ToolDef

_SENSITIVE_KEYS: frozenset[str] = frozenset(
    {"authorization", "cookie", "api_key", "token", "secret"}
)


def _sanitize_messages(messages: Any) -> Any:
    """Recursively redact sensitive string values in a messages structure."""
    if isinstance(messages, list):
        return [_sanitize_messages(item) for item in messages]
    if isinstance(messages, dict):
        result: dict[str, Any] = {}
        for k, v in messages.items():
            if isinstance(k, str) and k.lower() in _SENSITIVE_KEYS and isinstance(v, str):
                result[k] = "***REDACTED***"
            else:
                result[k] = _sanitize_messages(v)
        return result
    return messages


def _log_streaming_request(
    logger: logging.Logger,
    name: str,
    model: str,
    messages: list[Any],
    tools: list[Any] | None,
) -> None:
    """Log a streaming request. Metadata at DEBUG; full payload only when DEBUG is active."""
    roles = [m.get("role", "?") if isinstance(m, dict) else "?" for m in messages]
    tool_names = [
        (t.get("function", {}).get("name") or t.get("name", "?")) if isinstance(t, dict) else "?"
        for t in (tools or [])
    ]
    logger.debug(
        "%s streaming request: model=%s messages=%d roles=%s tools=%s",
        name,
        model,
        len(messages),
        roles,
        tool_names,
    )
    if logger.isEnabledFor(logging.DEBUG):
        sanitized = _sanitize_messages(copy.deepcopy(messages))
        payload: dict[str, Any] = {"model": model, "messages": sanitized}
        if tools:
            payload["tools"] = tools
        logger.debug("%s request payload: %s", name, json.dumps(payload, ensure_ascii=False))


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


def _tool_def_to_json_schema(tooldef: ToolDef) -> dict[str, Any]:
    """Convert a ToolDef to a JSON Schema object (the inner schema body)."""
    properties: dict[str, Any] = {}
    required: list[str] = []
    for arg in tooldef.args:
        properties[arg.name] = {"type": arg.type, "description": arg.desc}
        if arg.required:
            required.append(arg.name)
    return {"type": "object", "properties": properties, "required": required}


def _parse_tool_call_args(raw: str) -> tuple[dict[str, Any], str | None]:
    """Parse tool call JSON arguments; returns (args_dict, error_or_None)."""
    if not raw:
        return {}, None
    try:
        result: dict[str, Any] = json.loads(raw)
        return result, None
    except json.JSONDecodeError:
        return {}, f"Invalid JSON arguments: {raw!r}"


def _is_context_overflow(
    e: Any,
    substrings: tuple[str, ...],
    code: str | None = None,
) -> bool:
    """Return True iff exception indicates a context-length overflow.

    Matches by SDK ``code`` attribute (when ``code`` is given) or by
    case-insensitive substring search on ``str(e)``.
    """
    if code is not None and getattr(e, "code", None) == code:
        return True
    msg = str(e).lower()
    return any(sub in msg for sub in substrings)
