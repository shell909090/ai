"""OpenAI backend implementation."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any, Literal

from little_agent.tools.protocol import ToolMap
from little_agent.types import SessionUpdate

from ._base import _StreamAccumulator, _StreamingBackend
from ._utils import (
    _log_streaming_request,
    _log_streaming_response,
    _parse_tool_call_args,
    _tool_def_to_json_schema,
)
from .protocol import BackendSession, BackendToolCall, BackendTurnResult

logger = logging.getLogger(__name__)


def _tool_map_to_openai_functions(tool_map: ToolMap) -> list[dict[str, Any]]:
    """Convert ToolMap to OpenAI function definitions."""
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": tooldef.desc,
                "parameters": _tool_def_to_json_schema(tooldef),
            },
        }
        for name, tooldef in tool_map.items()
    ]


def _chain_to_messages(session: BackendSession) -> list[dict[str, Any]]:
    """Convert session messages to OpenAI API format.

    Prepends a system message when system_prompt or summaries are set.
    """
    messages: list[dict[str, Any]] = []

    parts = [p for p in [session.system_prompt] + list(session.summaries) if p]
    if parts:
        messages.append({"role": "system", "content": "\n\n".join(parts)})

    for node in session.messages:
        for msg in node.to_openai():
            messages.append(msg)

    return messages


def _accumulate_tool_call_delta(tool_blocks: dict[int, dict[str, Any]], tc_delta: Any) -> None:
    """Merge one streaming tool-call delta into the running accumulator."""
    idx = tc_delta.index
    if idx not in tool_blocks:
        tool_blocks[idx] = {"id": "", "name": "", "arguments": ""}
    if tc_delta.id:
        tool_blocks[idx]["id"] += tc_delta.id
    if tc_delta.function:
        if tc_delta.function.name:
            tool_blocks[idx]["name"] += tc_delta.function.name
        if tc_delta.function.arguments:
            tool_blocks[idx]["arguments"] += tc_delta.function.arguments


_OPEN_TAG = "<think>"
_CLOSE_TAG = "</think>"


class ThinkTagParser:
    """Streaming parser that detects <think>...</think> tags and routes content."""

    def __init__(self) -> None:
        self._buf = ""
        self._thinking = False

    def feed(self, text: str) -> list[SessionUpdate]:
        """Feed a text chunk; returns list of SessionUpdates to emit immediately."""
        self._buf += text
        return self._flush_safe()

    def _emit_type(self) -> Literal["agent_message_chunk", "thinking_chunk"]:
        return "thinking_chunk" if self._thinking else "agent_message_chunk"

    def flush(self) -> list[SessionUpdate]:
        """Flush remaining buffer at stream end; returns any pending SessionUpdates."""
        if not self._buf:
            return []
        updates = [SessionUpdate(type=self._emit_type(), data={"text": self._buf})]
        self._buf = ""
        return updates

    def _flush_safe(self) -> list[SessionUpdate]:
        updates: list[SessionUpdate] = []
        while self._buf:
            tag = _CLOSE_TAG if self._thinking else _OPEN_TAG
            idx = self._buf.find(tag)
            if idx != -1:
                # Complete tag found: emit content before it, discard tag, switch mode.
                before = self._buf[:idx]
                if before:
                    updates.append(SessionUpdate(type=self._emit_type(), data={"text": before}))
                self._buf = self._buf[idx + len(tag) :]
                self._thinking = not self._thinking
            else:
                # No complete tag; retain a lookahead suffix to guard cross-chunk boundaries.
                lookahead = len(tag) - 1
                safe_len = len(self._buf) - lookahead
                if safe_len <= 0:
                    break
                safe = self._buf[:safe_len]
                updates.append(SessionUpdate(type=self._emit_type(), data={"text": safe}))
                self._buf = self._buf[safe_len:]
                break
        return updates


def _process_delta(delta: Any, acc: _StreamAccumulator) -> tuple[str | None, list[SessionUpdate]]:
    """Collect raw content and SessionUpdate events from one streaming delta.

    Returns (raw_content, updates): ``raw_content`` is fed through
    ThinkTagParser by the caller; ``updates`` are reasoning / tool events
    ready to yield directly.
    """
    raw_content: str | None = None
    updates: list[SessionUpdate] = []
    if delta.content:
        raw_content = delta.content
    reasoning_raw = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None)
    reasoning = reasoning_raw if isinstance(reasoning_raw, str) else None
    if reasoning:
        acc.thinking.append(reasoning)
        updates.append(SessionUpdate(type="thinking_chunk", data={"text": reasoning}))
    if delta.tool_calls:
        for tc_delta in delta.tool_calls:
            _accumulate_tool_call_delta(acc.tool_blocks, tc_delta)
    return raw_content, updates


def _drain_parser(updates: list[SessionUpdate], acc: _StreamAccumulator) -> list[SessionUpdate]:
    """Route parser output into accumulators; return same updates for yielding."""
    for u in updates:
        if u.type == "agent_message_chunk":
            acc.text.append(u.data["text"])  # type: ignore[arg-type]
        else:
            acc.thinking.append(u.data["text"])  # type: ignore[arg-type]
    return updates


def _extract_chunk_usage(usage_obj: Any) -> dict[str, int]:
    """Extract token counts from a streaming chunk's usage object."""
    usage: dict[str, int] = {
        "input_tokens": usage_obj.prompt_tokens,
        "output_tokens": usage_obj.completion_tokens,
    }
    if hasattr(usage_obj, "prompt_tokens_details") and usage_obj.prompt_tokens_details:
        cached = getattr(usage_obj.prompt_tokens_details, "cached_tokens", None)
        if cached is not None:
            usage["cached_tokens"] = cached
    return usage


def _postprocess_orphaned_think(acc: _StreamAccumulator) -> None:
    """Strip orphaned </think> from acc.text and, when needed, recover thinking content.

    Two scenarios handled:
    1. Vendor sends thinking via delta.reasoning AND emits </think> in delta.content
       (e.g. stepfun): acc.thinking already populated; just strip the tag from text.
    2. Vendor strips <think> but leaves thinking text + </think> in delta.content
       (e.g. older LiteLLM behaviour): acc.thinking empty; move content before </think>
       into acc.thinking.
    """
    full_text = "".join(acc.text)
    close_idx = full_text.find(_CLOSE_TAG)
    if close_idx == -1:
        return
    text_part = full_text[close_idx + len(_CLOSE_TAG) :]
    if acc.thinking:
        # Thinking already captured via delta.reasoning/reasoning_content.
        # The </think> in delta.content is redundant — strip it.
        logger.debug(
            "stripping orphaned </think> from output (thinking already set); text_after_chars=%d",
            len(text_part),
        )
        acc.text = [text_part] if text_part else []
    else:
        # No thinking accumulated yet — content before </think> is the thinking text.
        thinking_part = full_text[:close_idx]
        logger.debug(
            "orphaned </think>: <think> was stripped by proxy/model; "
            "thinking_chars=%d text_after_chars=%d thinking_preview=%r",
            len(thinking_part),
            len(text_part),
            thinking_part[:200],
        )
        acc.thinking = [thinking_part] if thinking_part else []
        acc.text = [text_part] if text_part else []


def _build_tool_calls(tool_blocks: dict[int, dict[str, Any]]) -> list[BackendToolCall]:
    """Build BackendToolCall list from accumulated streaming deltas."""
    result = []
    for tc_data in (tool_blocks[i] for i in sorted(tool_blocks.keys())):
        raw_args = tc_data["arguments"]
        arguments, error = _parse_tool_call_args(raw_args)
        if error:
            logger.error("Failed to parse tool call arguments: %r", raw_args)
        result.append(
            BackendToolCall(
                call_id=tc_data["id"],
                tool_name=tc_data["name"],
                arguments=arguments,
                error=error,
            )
        )
    return result


_CONTEXT_OVERFLOW_SUBSTRINGS = (
    "maximum context length",
    "context window",
    "context length",
    "context_length_exceeded",
)


class OpenAIBackend(_StreamingBackend):
    """OpenAI backend implementation."""

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str | None = None,
        timeout: float = 60.0,
        max_concurrency: int = 1,
        context_window: int = 128000,
    ) -> None:
        import openai

        super().__init__(
            model=model,
            timeout=timeout,
            max_concurrency=max_concurrency,
            context_window=context_window,
        )
        if base_url is not None:
            self._client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
        else:
            self._client = openai.AsyncOpenAI(api_key=api_key)

    async def _open_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        session_id: str = "",
    ) -> Any:
        import openai

        try:
            return await asyncio.wait_for(
                self._client.chat.completions.create(  # type: ignore[call-overload]
                    model=self._model,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto" if tools else None,
                    stream=True,
                    stream_options={"include_usage": True},
                    user=session_id or None,
                ),
                timeout=self._timeout,
            )
        except (TimeoutError, openai.APIError) as e:
            self._raise_mapped(
                e, openai, _CONTEXT_OVERFLOW_SUBSTRINGS, code="context_length_exceeded"
            )

    async def _stream(
        self, session: BackendSession
    ) -> AsyncGenerator[SessionUpdate | BackendTurnResult, None]:
        """Stream response from OpenAI, yielding updates then a final BackendTurnResult."""
        async with self._sem:
            tool_map = session.get_turn_tool_map()
            messages = _chain_to_messages(session)
            tools = _tool_map_to_openai_functions(tool_map) if tool_map else None

            _log_streaming_request(logger, "OpenAI", self._model, messages, tools)

            start_time = time.perf_counter()
            stream = await self._open_stream(messages, tools, session.id)

            acc = _StreamAccumulator(finish_reason_raw="stop")
            parser = ThinkTagParser()

            async for chunk in stream:
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    fr = chunk.choices[0].finish_reason
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug("SSE chunk: %s", chunk.model_dump_json(exclude_unset=True))
                    if fr is not None:
                        acc.finish_reason_raw = fr
                    raw_content, direct_updates = _process_delta(delta, acc)
                    for update in direct_updates:
                        yield update
                    if raw_content:
                        for update in _drain_parser(parser.feed(raw_content), acc):
                            yield update
                if chunk.usage:
                    acc.usage = _extract_chunk_usage(chunk.usage)

            for update in _drain_parser(parser.flush(), acc):
                yield update

            _postprocess_orphaned_think(acc)

            elapsed = time.perf_counter() - start_time
            finish_reason: Literal["completed", "tool_call"] = (
                "tool_call" if acc.finish_reason_raw == "tool_calls" else "completed"
            )

            _log_streaming_response(
                logger, "OpenAI", self._model, acc.finish_reason_raw, acc.usage, elapsed
            )

            yield BackendTurnResult(
                output_text=acc.output_text(),
                tool_calls=_build_tool_calls(acc.tool_blocks),
                finish_reason=finish_reason,
                usage=acc.usage,
                thinking_text=acc.thinking_text(),
            )
