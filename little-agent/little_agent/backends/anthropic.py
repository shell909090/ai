"""Anthropic backend implementation."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any, Literal

from little_agent.agent.nodes import (
    AssistantResponseNode,
    Node,
    SummaryNode,
    ToolCallNode,
    ToolResultNode,
    UserPromptNode,
)
from little_agent.tools.protocol import ToolMap
from little_agent.types import SessionUpdate

from ._base import _StreamingBackend
from ._utils import (
    _format_tool_result,
    _log_streaming_request,
    _log_streaming_response,
    _tool_def_to_json_schema,
)
from .protocol import BackendToolCall, BackendTurnResult

if TYPE_CHECKING:
    from little_agent.agent.session import SessionCore

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


def _node_to_message(n: Node) -> list[dict[str, Any]]:
    """Convert a single node to one or more Anthropic messages.

    SummaryNode is not converted here; it is handled by _chain_to_messages.
    """
    if isinstance(n, UserPromptNode):
        content: str | list[Any]
        if isinstance(n.prompt, str):
            content = n.prompt
        else:
            content = json.dumps(n.prompt)
        return [{"role": "user", "content": content}]

    if isinstance(n, AssistantResponseNode):
        return [
            {
                "role": "assistant",
                "content": [{"type": "text", "text": n.text}],
            }
        ]

    if isinstance(n, ToolCallNode):
        content_blocks: list[dict[str, Any]] = []
        if n.output_text:
            content_blocks.append({"type": "text", "text": n.output_text})
        content_blocks.extend(
            [
                {
                    "type": "tool_use",
                    "id": call_id,
                    "name": call_data["tool_name"],
                    "input": call_data["arguments"],
                }
                for call_id, call_data in n.calls.items()
            ]
        )
        return [{"role": "assistant", "content": content_blocks}]

    if isinstance(n, ToolResultNode):
        tool_result_blocks: list[dict[str, Any]] = [
            {
                "type": "tool_result",
                "tool_use_id": call_id,
                "content": _format_tool_result(result),
            }
            for call_id, result in n.results.items()
        ]
        return [{"role": "user", "content": tool_result_blocks}]

    return []


def _chain_to_messages(
    session: "SessionCore",
) -> tuple[list[dict[str, Any]], str | None]:
    """Convert chain of nodes to Anthropic messages list.

    Returns (messages, system_injected) where system_injected is the text of
    the first SummaryNode in the chain (hoisted to the Anthropic system param),
    or None if no SummaryNode is present.  Subsequent SummaryNodes are rendered
    as regular user messages so history context is preserved.
    """
    messages: list[dict[str, Any]] = []
    node: Node | None = session.tail if hasattr(session, "tail") else None
    chain: list[Node] = []
    while node is not None:
        chain.append(node)
        node = node.prev
    chain.reverse()

    system_injected: str | None = None
    for n in chain:
        if isinstance(n, SummaryNode):
            if system_injected is None:
                # First SummaryNode is lifted to the Anthropic system parameter.
                system_injected = str(n.summary)
            else:
                # Subsequent SummaryNodes stay as user messages.
                messages.append({"role": "user", "content": str(n.summary)})
            continue
        for msg in _node_to_message(n):
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


def _handle_stream_event(
    event: Any,
    text_chunks: list[str],
    thinking_chunks: list[str],
    tool_blocks_acc: dict[int, dict[str, Any]],
) -> None:
    """Update accumulators from a single stream event (no yields)."""
    event_type = event.type
    if event_type == "content_block_start":
        block = event.content_block
        idx: int = event.index
        if block.type == "tool_use":
            tool_blocks_acc[idx] = {"id": block.id, "name": block.name, "input_json": ""}
    elif event_type == "content_block_delta":
        delta = event.delta
        idx = event.index
        delta_type = delta.type
        if delta_type == "text_delta":
            text_chunks.append(delta.text)
        elif delta_type == "thinking_delta":
            thinking_chunks.append(delta.thinking)
        elif delta_type == "input_json_delta" and idx in tool_blocks_acc:
            tool_blocks_acc[idx]["input_json"] += delta.partial_json


def _make_stream_update(event: Any) -> SessionUpdate | None:
    """Return a SessionUpdate to yield for chunk events, or None."""
    if event.type != "content_block_delta":
        return None
    delta = event.delta
    if delta.type == "text_delta":
        return SessionUpdate(type="agent_message_chunk", data={"text": delta.text})
    if delta.type == "thinking_delta":
        return SessionUpdate(type="thinking_chunk", data={"text": delta.thinking})
    return None


def _update_metadata(
    event: Any,
    finish_reason_raw: str,
    usage: dict[str, int] | None,
) -> tuple[str, dict[str, int] | None]:
    """Return updated (finish_reason_raw, usage) from a metadata event."""
    event_type = event.type
    if event_type == "message_delta":
        delta = event.delta
        if hasattr(delta, "stop_reason") and delta.stop_reason:
            finish_reason_raw = delta.stop_reason
        if hasattr(event, "usage") and event.usage:
            if usage is None:
                usage = {}
            usage.update(_extract_usage(event.usage))
    elif event_type == "message_start":
        msg = event.message
        if hasattr(msg, "usage") and msg.usage:
            if usage is None:
                usage = {}
            usage.update(_extract_usage(msg.usage))
    return finish_reason_raw, usage


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

        try:
            async with asyncio.timeout(self._timeout):
                async with self._client.messages.stream(**kwargs) as stream:
                    async for event in stream:
                        yield event
        except (TimeoutError, anthropic.APIError) as e:
            self._raise_mapped(e, anthropic, _CONTEXT_OVERFLOW_SUBSTRINGS)

    async def _stream(
        self, session: "SessionCore"
    ) -> AsyncGenerator[SessionUpdate | BackendTurnResult, None]:
        """Stream response from Anthropic, yielding updates then a final BackendTurnResult."""
        async with self._sem:
            tool_map = session.get_turn_tool_map()
            messages, system_injected = _chain_to_messages(session)
            tools = _tool_map_to_anthropic_tools(tool_map) if tool_map else None

            _log_streaming_request(logger, "Anthropic", self._model, messages, tools)

            start_time = time.perf_counter()

            text_chunks: list[str] = []
            thinking_chunks: list[str] = []
            # Accumulate tool input JSON per content block index
            tool_blocks_acc: dict[int, dict[str, Any]] = {}
            usage: dict[str, int] | None = None
            finish_reason_raw = "end_turn"

            async for event in self._generate_stream_inner(messages, tools, system_injected):
                _handle_stream_event(
                    event,
                    text_chunks,
                    thinking_chunks,
                    tool_blocks_acc,
                )
                finish_reason_raw, usage = _update_metadata(event, finish_reason_raw, usage)
                update = _make_stream_update(event)
                if update is not None:
                    yield update

            elapsed = time.perf_counter() - start_time

            # Build tool calls from accumulated data
            tool_calls: list[BackendToolCall] = []
            for idx in sorted(tool_blocks_acc.keys()):
                tb = tool_blocks_acc[idx]
                raw_input = tb["input_json"]
                tc_error: str | None = None
                if raw_input:
                    try:
                        arguments: dict[str, Any] = json.loads(raw_input)
                    except json.JSONDecodeError:
                        logger.error("Failed to parse tool call arguments: %r", raw_input)
                        arguments = {}
                        tc_error = f"Invalid JSON arguments: {raw_input!r}"
                else:
                    arguments = {}
                tool_calls.append(
                    BackendToolCall(
                        call_id=tb["id"],
                        tool_name=tb["name"],
                        arguments=arguments,
                        error=tc_error,
                    )
                )

            finish_reason: Literal["completed", "tool_call"] = (
                "tool_call" if finish_reason_raw == "tool_use" else "completed"
            )

            _log_streaming_response(
                logger, "Anthropic", self._model, finish_reason_raw, usage, elapsed
            )

            yield BackendTurnResult(
                output_text="".join(text_chunks),
                tool_calls=tool_calls,
                finish_reason=finish_reason,
                usage=usage,
                thinking_text="".join(thinking_chunks) or None,
            )
