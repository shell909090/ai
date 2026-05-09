"""Tool invocation pipeline for a single agent turn."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING, Literal

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
        self._session._append_node(node)
        return node

    def _create_tool_result_node(self) -> ToolResultNode:
        """Create and append a ToolResultNode."""
        node = ToolResultNode(
            id=str(uuid.uuid4()),
            prev=self._session.tail,
            results={},
        )
        self._session._append_node(node)
        return node

    def _check(
        self,
        tc: BackendToolCall,
        allowed_names: set[str] | None,
    ) -> tuple[Literal["allow", "deny", "ask"], str | None]:
        """Check if a tool call is allowed; return (action, error_msg)."""
        if allowed_names is not None and tc.tool_name not in allowed_names:
            return "deny", f"Tool not in allowed list: {tc.tool_name}"

        if self._session.agent.permissions is not None:
            return self._session.agent.permissions.check(tc.tool_name), None
        return "allow", None

    async def _ask_permissions(
        self,
        needs_permission: list[BackendToolCall],
        tool_result_node: ToolResultNode,
    ) -> list[BackendToolCall]:
        """Request permission for 'ask' calls; return approved ones."""
        approved: list[BackendToolCall] = []
        for tc in needs_permission:
            granted = await self._session.agent.client.request_permission(
                self._session,
                tc.tool_name,
                {"arguments": tc.arguments},
            )
            if granted:
                approved.append(tc)
            else:
                tool_result_node.results[tc.call_id] = {
                    "status": "failed",
                    "content": "Permission denied",
                }
        return approved

    async def _invoke_tools(
        self, result: BackendTurnResult, tool_result_node: ToolResultNode
    ) -> None:
        """Invoke tools concurrently and populate tool_result_node."""
        from little_agent.agent.context import current_session

        allowed_names = (
            set(self._session._turn_allowed_tools)
            if self._session._turn_allowed_tools is not None
            else None
        )

        allowed_calls: list[BackendToolCall] = []
        needs_permission: list[BackendToolCall] = []
        for tc in result.tool_calls:
            action, error_msg = self._check(tc, allowed_names)
            if action == "deny":
                tool_result_node.results[tc.call_id] = {
                    "status": "failed",
                    "content": error_msg or "Permission denied",
                }
                continue
            if action == "ask":
                needs_permission.append(tc)
                continue
            allowed_calls.append(tc)

        approved = await self._ask_permissions(needs_permission, tool_result_node)
        allowed_calls.extend(approved)

        token = current_session.set(self._session)
        try:

            async def _call(name: str, args: dict[str, JSONValue]) -> JSONValue:
                return await self._session.agent.tools[name](args)

            tasks = [_call(tc.tool_name, tc.arguments) for tc in allowed_calls]
            tool_results = await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            current_session.reset(token)

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
