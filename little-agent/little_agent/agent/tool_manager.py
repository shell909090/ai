"""Tool registry and per-turn tool invocation pipeline.

ToolManager: long-lived registry mapping tool name -> (ToolDef, callable).
invoke_turn_tools(): per-turn pipeline that creates AssistantNode /
ToolResultNode, runs permission checks, gathers tool execution, and emits
tool_call / tool_call_update events. It takes the session as a parameter
rather than holding it as state because nothing about the pipeline
outlives a single turn.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import TYPE_CHECKING

from little_agent.backends.protocol import BackendToolCall, BackendTurnResult
from little_agent.tools.protocol import AsyncToolFn, ToolDef, ToolMap, ToolProvider
from little_agent.types import JSONValue, SessionUpdate

from .nodes import AssistantNode, ToolResultNode

if TYPE_CHECKING:
    from .session import SessionCore

logger = logging.getLogger(__name__)


class ToolManager:
    """Implements ToolRegistry: aggregates ToolProviders."""

    def __init__(self) -> None:
        self._registry: dict[str, tuple[ToolDef, AsyncToolFn]] = {}

    def register(self, provider: ToolProvider) -> None:
        """Register all tools from a provider; raises ValueError on name conflict."""
        for name, tooldef, fn in provider:
            if name in self._registry:
                raise ValueError(f"Tool '{name}' already registered")
            self._registry[name] = (tooldef, fn)

    def desc_tool(
        self,
        names: set[str] | None = None,
        *,
        exclude: set[str] | None = None,
    ) -> ToolMap:
        """Return ToolMap for the given name set, minus any excluded names."""
        result = (
            {n: td for n, (td, _) in self._registry.items()}
            if names is None
            else {n: td for n, (td, _) in self._registry.items() if n in names}
        )
        if exclude:
            result = {n: td for n, td in result.items() if n not in exclude}
        return result

    def __getitem__(self, name: str) -> AsyncToolFn:
        """Return the callable for a tool; raises KeyError if not found."""
        if name not in self._registry:
            raise KeyError(f"Tool '{name}' not found")
        return self._registry[name][1]


# ---------------------------------------------------------------------------
# Per-turn tool invocation pipeline
# ---------------------------------------------------------------------------


def _truncate_tool_result(content: JSONValue, max_chars: int) -> JSONValue:
    """Return content unchanged if within max_chars; otherwise serialize, truncate, and annotate."""
    serialized = json.dumps(content, ensure_ascii=False)
    if len(serialized) <= max_chars:
        return content
    original_len = len(serialized)
    logger.warning("tool result truncated: %d chars -> %d chars", original_len, max_chars)
    return (
        f"{serialized[:max_chars]}\n"
        f"[TRUNCATED: {original_len} chars total, showing first {max_chars}]"
    )


def _create_assistant_node(session: SessionCore, result: BackendTurnResult) -> AssistantNode:
    """Create and append an AssistantNode for a tool call result."""
    node = AssistantNode(
        id=str(uuid.uuid4()),
        text=result.output_text or "",
        thinking=result.thinking_text or "",
        tool_calls={
            tc.call_id: {"tool_name": tc.tool_name, "arguments": tc.arguments}
            for tc in result.tool_calls
        },
    )
    session.append_node(node)
    return node


def _create_tool_result_node(session: SessionCore) -> ToolResultNode:
    """Create and append a ToolResultNode."""
    node = ToolResultNode(
        id=str(uuid.uuid4()),
        results={},
    )
    session.append_node(node)
    return node


async def _run_tool_gather(
    session: SessionCore,
    allowed_calls: list[BackendToolCall],
    tool_result_node: ToolResultNode,
) -> tuple[list[BackendToolCall], list[JSONValue | BaseException]]:
    """Execute tools via gather, or skip all if already cancelled."""
    from little_agent.agent.context import current_session

    if session.is_cancel_requested:
        for tc in allowed_calls:
            tool_result_node.results[tc.call_id] = {
                "status": "cancelled",
                "content": "Cancelled before execution",
            }
        return [], []

    token = current_session.set(session)
    try:

        async def _call(name: str, args: dict[str, JSONValue]) -> JSONValue:
            return await session.agent.tools[name](args)

        tasks = [_call(tc.tool_name, tc.arguments) for tc in allowed_calls]
        results: list[JSONValue | BaseException] = await asyncio.gather(
            *tasks, return_exceptions=True
        )
        return allowed_calls, results
    finally:
        current_session.reset(token)


async def _invoke_tools(
    session: SessionCore,
    result: BackendTurnResult,
    tool_result_node: ToolResultNode,
) -> None:
    """Invoke tools concurrently and populate tool_result_node."""
    allowed_tools = session.turn_allowed_tools
    allowed_names = set(allowed_tools) if allowed_tools is not None else None

    allowed_calls: list[BackendToolCall] = []
    for tc in result.tool_calls:
        if tc.error is not None:
            tool_result_node.results[tc.call_id] = {
                "status": "failed",
                "content": tc.error,
            }
            continue
        if allowed_names is not None and tc.tool_name not in allowed_names:
            tool_result_node.results[tc.call_id] = {
                "status": "failed",
                "content": f"Tool not in allowed list: {tc.tool_name}",
            }
            continue
        granted = await session.agent.permissions.request_permission(
            session, tc.tool_name, {"arguments": tc.arguments}
        )
        if granted:
            allowed_calls.append(tc)
        else:
            tool_result_node.results[tc.call_id] = {
                "status": "failed",
                "content": "Permission denied",
            }

    allowed_calls, tool_results = await _run_tool_gather(session, allowed_calls, tool_result_node)

    for tc, res in zip(allowed_calls, tool_results, strict=True):
        if session.is_cancel_requested:
            tool_result_node.results[tc.call_id] = {
                "status": "cancelled",
                "content": "",
            }
        elif isinstance(res, BaseException):
            tool_result_node.results[tc.call_id] = {
                "status": "failed",
                "content": str(res),
            }
        else:
            tool_result_node.results[tc.call_id] = {
                "status": "completed",
                "content": _truncate_tool_result(res, session.agent.max_tool_result_chars),
            }

    for tc in result.tool_calls:
        await session.agent.client.update(
            session,
            SessionUpdate(
                type="tool_call_update",
                data={
                    "call_id": tc.call_id,
                    "status": tool_result_node.results[tc.call_id]["status"],
                    "content": tool_result_node.results[tc.call_id]["content"],
                },
            ),
        )


async def invoke_turn_tools(
    session: SessionCore,
    result: BackendTurnResult,
    partial_output: str,
    did_stream: bool = False,
) -> str:
    """Handle a tool_call BackendTurnResult and return the updated partial_output.

    Appends AssistantNode (frozen) and ToolResultNode (mutable) to the session,
    fires on_tool_call hook with session.messages[-1] == the AssistantNode, executes
    tools concurrently with permission + allowlist checks, freezes
    ToolResultNode, fires on_tool_result hook.
    """
    partial_output = result.output_text or partial_output
    if result.output_text and not did_stream:
        await session.agent.client.update(
            session,
            SessionUpdate(
                type="agent_message_chunk",
                data={"text": result.output_text},
            ),
        )

    tool_call_node = _create_assistant_node(session, result)
    await session.agent.client.update(
        session,
        SessionUpdate(
            type="tool_call",
            data={"calls": tool_call_node.tool_calls},  # type: ignore[dict-item]
        ),
    )
    await session.call_hooks("on_tool_call", session)

    tool_result_node = _create_tool_result_node(session)
    await _invoke_tools(session, result, tool_result_node)
    await session.call_hooks("on_tool_result", session)

    return partial_output
