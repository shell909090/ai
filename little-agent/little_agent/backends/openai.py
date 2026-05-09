"""OpenAI backend implementation."""

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


def _tool_map_to_openai_functions(tool_map: ToolMap) -> list[dict[str, Any]]:
    """Convert ToolMap to OpenAI function definitions."""
    functions = []
    for name, (desc, args) in tool_map.items():
        properties: dict[str, Any] = {}
        required: list[str] = []
        for arg_name, arg_type, arg_desc, arg_required in args:
            properties[arg_name] = {
                "type": arg_type,
                "description": arg_desc,
            }
            if arg_required:
                required.append(arg_name)
        functions.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": desc,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                },
            }
        )
    return functions


def _format_tool_result(result: dict[str, Any]) -> str:
    """Format tool result dict as multi-line k: v text."""
    lines = []
    for k, v in result.items():
        if isinstance(v, str):
            lines.append(f"{k}: {v}")
        else:
            lines.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
    return "\n".join(lines)


def _node_to_message(n: Node) -> list[dict[str, Any]]:
    """Convert a single node to one or more OpenAI messages."""
    if isinstance(n, UserPromptNode):
        content = n.prompt if isinstance(n.prompt, str) else json.dumps(n.prompt)
        return [{"role": "user", "content": content}]
    if isinstance(n, AssistantResponseNode):
        return [{"role": "assistant", "content": n.text}]
    if isinstance(n, ToolCallNode):
        tool_calls = [
            {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": call_data["tool_name"],
                    "arguments": json.dumps(call_data["arguments"]),
                },
            }
            for call_id, call_data in n.calls.items()
        ]
        return [{"role": "assistant", "tool_calls": tool_calls}]
    if isinstance(n, ToolResultNode):
        return [
            {
                "role": "tool",
                "tool_call_id": call_id,
                "content": _format_tool_result(result),
            }
            for call_id, result in n.results.items()
        ]
    if isinstance(n, SummaryNode):
        return [{"role": "system", "content": str(n.summary)}]
    return []


def _chain_to_messages(session: "SessionCore" | Node) -> list[dict[str, Any]]:
    """Convert chain of nodes to OpenAI messages, injecting memory if present."""
    messages: list[dict[str, Any]] = []
    node = session.tail if hasattr(session, "tail") else session
    chain: list[Node] = []
    while node is not None:
        chain.append(node)
        node = node.prev
    chain.reverse()

    system_injected = False
    for n in chain:
        for msg in _node_to_message(n):
            if msg["role"] == "system":
                if not system_injected:
                    messages.insert(0, msg)
                    system_injected = True
            else:
                messages.append(msg)

    return messages


def _accumulate_tool_call_delta(tool_calls_acc: dict[int, dict[str, str]], tc_delta: Any) -> None:
    """Merge one streaming tool-call delta into the running accumulator."""
    idx = tc_delta.index
    if idx not in tool_calls_acc:
        tool_calls_acc[idx] = {"id": "", "name": "", "arguments": ""}
    if tc_delta.id:
        tool_calls_acc[idx]["id"] += tc_delta.id
    if tc_delta.function:
        if tc_delta.function.name:
            tool_calls_acc[idx]["name"] += tc_delta.function.name
        if tc_delta.function.arguments:
            tool_calls_acc[idx]["arguments"] += tc_delta.function.arguments


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


def _process_delta(
    delta: Any,
    thinking_chunks: list[str],
    tool_calls_acc: dict[int, dict[str, str]],
) -> tuple[str | None, list[SessionUpdate]]:
    """Collect raw content and SessionUpdate events from one streaming delta.

    Returns (raw_content, updates) where raw_content is the delta.content string
    (if any) to be fed through ThinkTagParser by the caller, and updates contains
    any thinking/tool events ready to emit directly.
    """
    raw_content: str | None = None
    updates: list[SessionUpdate] = []
    if delta.content:
        raw_content = delta.content
    reasoning = getattr(delta, "reasoning_content", None)
    if reasoning:
        thinking_chunks.append(reasoning)
        updates.append(SessionUpdate(type="thinking_chunk", data={"text": reasoning}))
    if delta.tool_calls:
        for tc_delta in delta.tool_calls:
            _accumulate_tool_call_delta(tool_calls_acc, tc_delta)
    return raw_content, updates


def _drain_parser(
    updates: list[SessionUpdate],
    text_chunks: list[str],
    thinking_chunks: list[str],
) -> list[SessionUpdate]:
    """Route parser output into accumulators; return same updates for yielding."""
    for u in updates:
        if u.type == "agent_message_chunk":
            text_chunks.append(u.data["text"])  # type: ignore[arg-type]
        else:
            thinking_chunks.append(u.data["text"])  # type: ignore[arg-type]
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


def _build_tool_calls(tool_calls_acc: dict[int, dict[str, str]]) -> list[BackendToolCall]:
    """Build BackendToolCall list from accumulated streaming deltas."""
    return [
        BackendToolCall(
            call_id=tc_data["id"],
            tool_name=tc_data["name"],
            arguments=json.loads(tc_data["arguments"]) if tc_data["arguments"] else {},
        )
        for tc_data in (tool_calls_acc[i] for i in sorted(tool_calls_acc.keys()))
    ]


_CONTEXT_OVERFLOW_SUBSTRINGS = (
    "maximum context length",
    "context window",
    "context length",
    "context_length_exceeded",
)


def _is_context_overflow(e: Any) -> bool:
    if getattr(e, "code", None) == "context_length_exceeded":
        return True
    msg = str(e).lower()
    return any(sub in msg for sub in _CONTEXT_OVERFLOW_SUBSTRINGS)


class OpenAIBackend:
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

        if base_url is not None:
            self._client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
        else:
            self._client = openai.AsyncOpenAI(api_key=api_key)
        self._model = model
        self._timeout = timeout
        self._sem = asyncio.Semaphore(max_concurrency)
        self.context_window = context_window

    def generate(self, session: SessionCore) -> AsyncIterator[SessionUpdate | BackendTurnResult]:
        """Return async iterator streaming OpenAI response."""
        return self._generate_stream(session)

    async def _open_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
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
                ),
                timeout=self._timeout,
            )
        except TimeoutError as e:
            raise BackendTimeoutError(f"Backend API call timed out after {self._timeout}s") from e
        except openai.BadRequestError as e:
            if _is_context_overflow(e):
                raise ContextOverflowError(str(e)) from e
            raise

    async def _generate_stream(
        self, session: SessionCore
    ) -> AsyncGenerator[SessionUpdate | BackendTurnResult, None]:
        """Stream response from OpenAI, yielding updates then a final BackendTurnResult."""
        async with self._sem:
            tool_map = session.get_turn_tool_map()
            messages = _chain_to_messages(session)
            tools = _tool_map_to_openai_functions(tool_map) if tool_map else None

            logger.debug(
                "OpenAI streaming request: model=%s messages=%s tools=%s",
                self._model,
                messages,
                tools,
            )

            start_time = time.perf_counter()
            stream = await self._open_stream(messages, tools)

            text_chunks: list[str] = []
            thinking_chunks: list[str] = []
            tool_calls_acc: dict[int, dict[str, str]] = {}
            usage: dict[str, int] | None = None
            finish_reason_raw = "stop"
            parser = ThinkTagParser()

            async for chunk in stream:
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    fr = chunk.choices[0].finish_reason
                    if fr is not None:
                        finish_reason_raw = fr
                    raw_content, direct_updates = _process_delta(
                        delta, thinking_chunks, tool_calls_acc
                    )
                    for update in direct_updates:
                        yield update
                    if raw_content:
                        for update in _drain_parser(
                            parser.feed(raw_content), text_chunks, thinking_chunks
                        ):
                            yield update
                if chunk.usage:
                    usage = _extract_chunk_usage(chunk.usage)

            for update in _drain_parser(parser.flush(), text_chunks, thinking_chunks):
                yield update

            elapsed = time.perf_counter() - start_time
            finish_reason: Literal["completed", "tool_call", "cancelled"] = (
                "tool_call" if finish_reason_raw == "tool_calls" else "completed"
            )

            logger.info(
                "OpenAI streaming response: model=%s finish_reason=%s "
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
                tool_calls=_build_tool_calls(tool_calls_acc),
                finish_reason=finish_reason,
                usage=usage,
                thinking_text="".join(thinking_chunks) or None,
            )
