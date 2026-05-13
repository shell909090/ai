"""Anthropic backend implementation."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any, Literal

from little_agent.agent.nodes import SummaryNode
from little_agent.agent.protocol import SessionUpdate
from little_agent.tools.protocol import ToolMap

from ._base import _iter_chain, _StreamAccumulator, _StreamingBackend
from ._utils import (
    _log_streaming_request,
    _log_streaming_response,
    _parse_tool_call_args,
    _tool_def_to_json_schema,
)
from .protocol import BackendSession, BackendToolCall, BackendTurnResult

logger = logging.getLogger(__name__)


def _tool_map_to_anthropic_tools(tool_map: ToolMap) -> list[dict[str, Any]]:
    """Convert ToolMap to Anthropic tool definitions."""
    return [
        {
            "name": name,
            "description": tooldef.desc,
            "input_schema": _tool_def_to_json_schema(tooldef),
        }
        for name, tooldef in tool_map.items()
    ]


def _chain_to_messages(
    session: BackendSession,
) -> tuple[list[dict[str, Any]], str | None]:
    """Convert chain of nodes to Anthropic messages list.

    Returns (messages, system_injected) where system_injected is the text of
    the first SummaryNode in the chain (hoisted to the Anthropic system param),
    or None if no SummaryNode is present.  Subsequent SummaryNodes are rendered
    as regular user messages so history context is preserved.
    """
    messages: list[dict[str, Any]] = []
    chain = _iter_chain(session)

    system_injected: str | None = None
    for n in chain:
        if isinstance(n, SummaryNode):
            if system_injected is None:
                # First SummaryNode is lifted to the Anthropic system parameter.
                system_injected = str(n.summary)
                continue
            # Subsequent SummaryNodes stay as regular messages via to_anthropic().
        for msg in n.to_anthropic():
            messages.append(msg)

    return messages, system_injected


_CONTEXT_OVERFLOW_SUBSTRINGS = (
    "prompt is too long",
    "too many tokens",
    "maximum context length",
)


def _extract_usage(usage_obj: Any) -> dict[str, int]:
    """Extract token counts from Anthropic usage object."""
    usage: dict[str, int] = {}
    if hasattr(usage_obj, "input_tokens") and usage_obj.input_tokens is not None:
        usage["input_tokens"] = int(usage_obj.input_tokens)
    if hasattr(usage_obj, "output_tokens") and usage_obj.output_tokens is not None:
        usage["output_tokens"] = int(usage_obj.output_tokens)
    if hasattr(usage_obj, "cache_read_input_tokens") and usage_obj.cache_read_input_tokens:
        usage["cached_tokens"] = int(usage_obj.cache_read_input_tokens)
    return usage


def _merge_usage(acc: _StreamAccumulator, usage_obj: Any) -> None:
    """Merge usage data from a stream event into the accumulator."""
    if acc.usage is None:
        acc.usage = {}
    acc.usage.update(_extract_usage(usage_obj))


def _handle_content_delta(event: Any, acc: _StreamAccumulator) -> SessionUpdate | None:
    """Dispatch a content_block_delta event; update acc and optionally yield update."""
    delta = event.delta
    match delta.type:
        case "text_delta":
            acc.text.append(delta.text)
            return SessionUpdate(type="agent_message_chunk", data={"text": delta.text})
        case "thinking_delta":
            acc.thinking.append(delta.thinking)
            return SessionUpdate(type="thinking_chunk", data={"text": delta.thinking})
        case "input_json_delta":
            if event.index in acc.tool_blocks:
                acc.tool_blocks[event.index]["input_json"] += delta.partial_json
    return None


def _process_event(event: Any, acc: _StreamAccumulator) -> SessionUpdate | None:
    """Update ``acc`` from one stream event; return SessionUpdate to yield, or None."""
    match event.type:
        case "content_block_start":
            block = event.content_block
            if block.type == "tool_use":
                acc.tool_blocks[event.index] = {
                    "id": block.id,
                    "name": block.name,
                    "input_json": "",
                }
        case "content_block_delta":
            return _handle_content_delta(event, acc)
        case "message_start":
            msg = event.message
            if hasattr(msg, "usage") and msg.usage:
                _merge_usage(acc, msg.usage)
        case "message_delta":
            delta = event.delta
            if hasattr(delta, "stop_reason") and delta.stop_reason:
                acc.finish_reason_raw = delta.stop_reason
            if hasattr(event, "usage") and event.usage:
                _merge_usage(acc, event.usage)
    return None


def _log_anthropic_event(logger: logging.Logger, event: Any) -> None:
    """Log one Anthropic stream event as raw JSON at DEBUG level."""
    if hasattr(event, "model_dump_json"):
        logger.debug("SSE event: %s", event.model_dump_json(exclude_unset=True))
    else:
        logger.debug("SSE event: %r", event)


def _build_tool_calls(acc: _StreamAccumulator) -> list[BackendToolCall]:
    """Build BackendToolCall list from Anthropic accumulated stream blocks."""
    tool_calls: list[BackendToolCall] = []
    for idx in sorted(acc.tool_blocks.keys()):
        tb = acc.tool_blocks[idx]
        arguments, error = _parse_tool_call_args(tb["input_json"])
        if error:
            logger.error("Failed to parse tool call arguments: %r", tb["input_json"])
        tool_calls.append(
            BackendToolCall(
                call_id=tb["id"],
                tool_name=tb["name"],
                arguments=arguments,
                error=error,
            )
        )
    return tool_calls


class AnthropicBackend(_StreamingBackend):
    """Anthropic backend implementation."""

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str | None = None,
        timeout: float = 60.0,
        max_concurrency: int = 1,
        context_window: int = 128000,
        system: str | None = None,
        max_tokens: int = 8192,
    ) -> None:
        import anthropic

        super().__init__(
            model=model,
            timeout=timeout,
            max_concurrency=max_concurrency,
            context_window=context_window,
        )
        if base_url is not None:
            self._client = anthropic.AsyncAnthropic(api_key=api_key, base_url=base_url)
        else:
            self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._system = system
        self._max_tokens = max_tokens

    async def _generate_stream_inner(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        system_injected: str | None = None,
        session_id: str = "",
    ) -> AsyncGenerator[Any, None]:
        """Inner generator that wraps the Anthropic stream with timeout and exception handling."""
        import anthropic

        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
        # system_injected (from the first SummaryNode) takes priority; fall back to self._system.
        effective_system = system_injected or self._system
        if effective_system:
            kwargs["system"] = effective_system
        if session_id:
            kwargs["metadata"] = {"user_id": session_id}

        try:
            async with asyncio.timeout(self._timeout):
                async with self._client.messages.stream(**kwargs) as stream:
                    async for event in stream:
                        yield event
        except (TimeoutError, anthropic.APIError) as e:
            self._raise_mapped(e, anthropic, _CONTEXT_OVERFLOW_SUBSTRINGS)

    async def _stream(
        self, session: BackendSession
    ) -> AsyncGenerator[SessionUpdate | BackendTurnResult, None]:
        """Stream response from Anthropic, yielding updates then a final BackendTurnResult."""
        async with self._sem:
            tool_map = session.get_turn_tool_map()
            messages, system_injected = _chain_to_messages(session)
            tools = _tool_map_to_anthropic_tools(tool_map) if tool_map else None

            _log_streaming_request(logger, "Anthropic", self._model, messages, tools)

            start_time = time.perf_counter()

            acc = _StreamAccumulator(finish_reason_raw="end_turn")

            async for event in self._generate_stream_inner(
                messages, tools, system_injected, session.id
            ):
                if logger.isEnabledFor(logging.DEBUG):
                    _log_anthropic_event(logger, event)
                update = _process_event(event, acc)
                if update is not None:
                    yield update

            elapsed = time.perf_counter() - start_time

            tool_calls = _build_tool_calls(acc)

            finish_reason: Literal["completed", "tool_call"] = (
                "tool_call" if acc.finish_reason_raw == "tool_use" else "completed"
            )

            _log_streaming_response(
                logger, "Anthropic", self._model, acc.finish_reason_raw, acc.usage, elapsed
            )

            yield BackendTurnResult(
                output_text=acc.output_text(),
                tool_calls=tool_calls,
                finish_reason=finish_reason,
                usage=acc.usage,
                thinking_text=acc.thinking_text(),
            )
