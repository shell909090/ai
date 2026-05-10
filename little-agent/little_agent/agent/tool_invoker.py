"""Tool invocation pipeline for a single agent turn."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING

from little_agent.backends.protocol import BackendToolCall, BackendTurnResult
from little_agent.types import JSONValue, SessionUpdate

from .nodes import ToolCallNode, ToolResultNode

if TYPE_CHECKING:
    from .session import SessionCore

logger = logging.getLogger(__name__)


class ToolInvoker:
    """Handles the tool-call pipeline for a single agent turn."""

    def __init__(self, session: SessionCore) -> None:
        self._session = session

    async def invoke(self, result: BackendTurnResult, partial_output: str) -> str:
        """Handle a tool_call result and return the updated partial_output."""
        partial_output = result.output_text or partial_output
        if result.output_text:
            await self._session.agent.client.update(
                self._session,
                SessionUpdate(
                    type="agent_message_chunk",
                    data={"text": result.output_text},
                ),
            )

        tool_call_node = self._create_tool_call_node(result)
        await self._session.agent.client.update(
            self._session,
            SessionUpdate(
                type="tool_call",
                data={"calls": tool_call_node.calls},  # type: ignore[dict-item]
            ),
        )

        tool_result_node = self._create_tool_result_node()
        await self._invoke_tools(result, tool_result_node)
        if self._session.tail is not None:
            self._session.tail.freeze()

        return partial_output

    def _create_tool_call_node(self, result: BackendTurnResult) -> ToolCallNode:
        """Create and append a ToolCallNode."""
        node = ToolCallNode(
            id=str(uuid.uuid4()),
            prev=self._session.tail,
            calls={
                tc.call_id: {"tool_name": tc.tool_name, "arguments": tc.arguments}
                for tc in result.tool_calls
            },
        )
        self._session.append_node(node)
        return node

    def _create_tool_result_node(self) -> ToolResultNode:
        """Create and append a ToolResultNode."""
        node = ToolResultNode(
            id=str(uuid.uuid4()),
            prev=self._session.tail,
            results={},
        )
        self._session.append_node(node)
        return node

    async def _run_tool_gather(
        self,
        allowed_calls: list[BackendToolCall],
        tool_result_node: ToolResultNode,
    ) -> tuple[list[BackendToolCall], list[JSONValue | BaseException]]:
        """Execute tools via gather, or skip all if already cancelled."""
        from little_agent.agent.context import current_session

        if self._session._cancel_requested:
            for tc in allowed_calls:
                tool_result_node.results[tc.call_id] = {
                    "status": "cancelled",
                    "content": "Cancelled before execution",
                }
            return [], []

        token = current_session.set(self._session)
        try:

            async def _call(name: str, args: dict[str, JSONValue]) -> JSONValue:
                return await self._session.agent.tools[name](args)

            tasks = [_call(tc.tool_name, tc.arguments) for tc in allowed_calls]
            results: list[JSONValue | BaseException] = await asyncio.gather(
                *tasks, return_exceptions=True
            )
            return allowed_calls, results
        finally:
            current_session.reset(token)

    async def _invoke_tools(
        self, result: BackendTurnResult, tool_result_node: ToolResultNode
    ) -> None:
        """Invoke tools concurrently and populate tool_result_node."""
        allowed_names = (
            set(self._session._turn_allowed_tools)
            if self._session._turn_allowed_tools is not None
            else None
        )

        allowed_calls: list[BackendToolCall] = []
        for tc in result.tool_calls:
            if allowed_names is not None and tc.tool_name not in allowed_names:
                tool_result_node.results[tc.call_id] = {
                    "status": "failed",
                    "content": f"Tool not in allowed list: {tc.tool_name}",
                }
                continue
            granted = await self._session.agent.permissions.request_permission(
                self._session, tc.tool_name, {"arguments": tc.arguments}
            )
            if granted:
                allowed_calls.append(tc)
            else:
                tool_result_node.results[tc.call_id] = {
                    "status": "failed",
                    "content": "Permission denied",
                }

        allowed_calls, tool_results = await self._run_tool_gather(allowed_calls, tool_result_node)

        for tc, res in zip(allowed_calls, tool_results, strict=True):
            if self._session._cancel_requested:
                tool_result_node.results[tc.call_id] = {
                    "status": "cancelled",
                    "content": "",
                }
            elif isinstance(res, Exception):
                tool_result_node.results[tc.call_id] = {
                    "status": "failed",
                    "content": str(res),
                }
            else:
                tool_result_node.results[tc.call_id] = {
                    "status": "completed",
                    "content": res,
                }

        for tc in result.tool_calls:
            await self._session.agent.client.update(
                self._session,
                SessionUpdate(
                    type="tool_call_update",
                    data={
                        "call_id": tc.call_id,
                        "status": tool_result_node.results[tc.call_id]["status"],
                        "content": tool_result_node.results[tc.call_id]["content"],
                    },
                ),
            )
