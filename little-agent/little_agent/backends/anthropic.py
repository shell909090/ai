"""Anthropic backend implementation."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator, AsyncIterator
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

from .exceptions import BackendTimeoutError, ContextOverflowError
from .protocol import BackendToolCall, BackendTurnResult

if TYPE_CHECKING:
    from little_agent.agent.core import SessionCore

logger = logging.getLogger(__name__)


def _tool_map_to_anthropic_tools(tool_map: ToolMap) -> list[dict[str, Any]]:
    """Convert ToolMap to Anthropic tool definitions."""
    tools = []
    for name, tooldef in tool_map.items():
        properties: dict[str, Any] = {}
        required: list[str] = []
        for arg in tooldef.args:
            properties[arg.name] = {"type": arg.type, "description": arg.desc}
            if arg.required:
                required.append(arg.name)
        tools.append(
            {
                "name": name,
                "description": tooldef.desc,
                "input_schema": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            }
        )
    return tools


def _format_tool_result_content(result: dict[str, Any]) -> str:
    """Format a tool result dict as a string for Anthropic tool_result content."""
    lines = []
    for k, v in result.items():
        if isinstance(v, str):
            lines.append(f"{k}: {v}")
        else:
            lines.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
    return "\n".join(lines)


def _node_to_message(n: Node) -> list[dict[str, Any]]:
    """Convert a single node to one or more Anthropic messages."""
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
        tool_use_blocks: list[dict[str, Any]] = [
            {
                "type": "tool_use",
                "id": call_id,
                "name": call_data["tool_name"],
                "input": call_data["arguments"],
            }
            for call_id, call_data in n.calls.items()
        ]
        return [{"role": "assistant", "content": tool_use_blocks}]

    if isinstance(n, ToolResultNode):
        tool_result_blocks: list[dict[str, Any]] = [
            {
                "type": "tool_result",
                "tool_use_id": call_id,
                "content": _format_tool_result_content(result),
            }
            for call_id, result in n.results.items()
        ]
        return [{"role": "user", "content": tool_result_blocks}]

    if isinstance(n, SummaryNode):
        return [{"role": "user", "content": str(n.summary)}]

    return []


def _chain_to_messages(session: "SessionCore") -> list[dict[str, Any]]:
    """Convert chain of nodes to Anthropic messages list."""
    messages: list[dict[str, Any]] = []
    node: Node | None = session.tail if hasattr(session, "tail") else None
    chain: list[Node] = []
    while node is not None:
        chain.append(node)
        node = node.prev
    chain.reverse()

    for n in chain:
        for msg in _node_to_message(n):
            messages.append(msg)

    return messages


_CONTEXT_OVERFLOW_SUBSTRINGS = (
    "prompt is too long",
    "too many tokens",
    "maximum context length",
)


def _is_context_overflow(e: Any) -> bool:
    """Check if an exception indicates context overflow."""
    msg = str(e).lower()
    return any(sub in msg for sub in _CONTEXT_OVERFLOW_SUBSTRINGS)


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
            usage = _extract_usage(event.usage)
    elif event_type == "message_start":
        msg = event.message
        if hasattr(msg, "usage") and msg.usage:
            usage = _extract_usage(msg.usage)
    return finish_reason_raw, usage


class AnthropicBackend:
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
    ) -> None:
        import anthropic

        if base_url is not None:
            self._client = anthropic.AsyncAnthropic(api_key=api_key, base_url=base_url)
        else:
            self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model
        self._timeout = timeout
        self._sem = asyncio.Semaphore(max_concurrency)
        self.context_window = context_window
        self._system = system

    def generate(self, session: "SessionCore") -> AsyncIterator[SessionUpdate | BackendTurnResult]:
        """Return async iterator streaming Anthropic response."""
        return self._generate_stream(session)

    async def _open_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> Any:
        """Open a streaming request to Anthropic with timeout."""
        import anthropic

        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self.context_window,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
        if self._system:
            kwargs["system"] = self._system

        try:
            return await asyncio.wait_for(
                self._client.messages.stream(**kwargs).__aenter__(),
                timeout=self._timeout,
            )
        except TimeoutError as e:
            raise BackendTimeoutError(f"Backend API call timed out after {self._timeout}s") from e
        except anthropic.BadRequestError as e:
            if _is_context_overflow(e):
                raise ContextOverflowError(str(e)) from e
            raise

    async def _generate_stream(
        self, session: "SessionCore"
    ) -> AsyncGenerator[SessionUpdate | BackendTurnResult, None]:
        """Stream response from Anthropic, yielding updates then a final BackendTurnResult."""
        async with self._sem:
            tool_map = session.get_turn_tool_map()
            messages = _chain_to_messages(session)
            tools = _tool_map_to_anthropic_tools(tool_map) if tool_map else None

            logger.debug(
                "Anthropic streaming request: model=%s messages=%s tools=%s",
                self._model,
                messages,
                tools,
            )

            start_time = time.perf_counter()
            stream = await self._open_stream(messages, tools)

            text_chunks: list[str] = []
            thinking_chunks: list[str] = []
            # Accumulate tool input JSON per content block index
            tool_blocks_acc: dict[int, dict[str, Any]] = {}
            usage: dict[str, int] | None = None
            finish_reason_raw = "end_turn"

            try:
                async for event in stream.event_stream:
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

            finally:
                await stream.__aexit__(None, None, None)

            elapsed = time.perf_counter() - start_time

            # Build tool calls from accumulated data
            tool_calls: list[BackendToolCall] = []
            for idx in sorted(tool_blocks_acc.keys()):
                tb = tool_blocks_acc[idx]
                raw_input = tb["input_json"]
                try:
                    arguments: dict[str, Any] = json.loads(raw_input) if raw_input else {}
                except json.JSONDecodeError:
                    arguments = {}
                tool_calls.append(
                    BackendToolCall(
                        call_id=tb["id"],
                        tool_name=tb["name"],
                        arguments=arguments,
                    )
                )

            finish_reason: Literal["completed", "tool_call", "cancelled"] = (
                "tool_call" if finish_reason_raw == "tool_use" else "completed"
            )

            logger.info(
                "Anthropic streaming response: model=%s finish_reason=%s "
                "input_tokens=%s output_tokens=%s cached_tokens=%s elapsed=%.3fs",
                self._model,
                finish_reason_raw,
                usage.get("input_tokens") if usage else None,
                usage.get("output_tokens") if usage else None,
                usage.get("cached_tokens") if usage else None,
                elapsed,
            )

            yield BackendTurnResult(
                output_text="".join(text_chunks),
                tool_calls=tool_calls,
                finish_reason=finish_reason,
                usage=usage,
                thinking_text="".join(thinking_chunks) or None,
            )
