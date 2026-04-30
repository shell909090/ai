from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING, Any

from little_agent.backends.protocol import BackendToolCall, BackendTurnResult
from little_agent.tools.protocol import ToolMap
from little_agent.types import ContentBlock, JSONValue, PromptReturn, SessionUpdate

from .exceptions import SessionBusyError
from .nodes import (
    AssistantResponseNode,
    Node,
    ToolCallNode,
    ToolResultNode,
    UserPromptNode,
    _rebuild_chain,
)
from .protocol import Agent, Compressor, Session

if TYPE_CHECKING:
    from little_agent.backends.protocol import Backend
    from little_agent.frontends.protocol import Client
    from little_agent.permissions import PermissionManager
    from little_agent.tools.protocol import ToolProvider

MAX_TURN_ITERATIONS = 10

_PendingItem = tuple[str | list[ContentBlock], list[str] | None, asyncio.Future[PromptReturn]]


class SessionCore(Session):
    def __init__(
        self,
        session_id: str,
        cwd: str | None,
        agent: AgentCore,
    ) -> None:
        self.id = session_id
        self.cwd = cwd
        self.agent = agent
        self.tail: Node | None = None
        self._active_turn: bool = False
        self._cancel_requested: bool = False
        self._pending_queue: asyncio.Queue[_PendingItem] = asyncio.Queue(maxsize=3)
        self._turn_allowed_tools: list[str] | None = None
        self._memory_text: str | None = None

    def get_turn_tool_map(self) -> ToolMap:
        """Return tool map filtered by _turn_allowed_tools (None = all tools)."""
        full_map = self.agent.tools.list()
        if self._turn_allowed_tools is None:
            return full_map
        return {k: v for k, v in full_map.items() if k in self._turn_allowed_tools}

    async def prompt(
        self, prompt: str | list[ContentBlock], allowed_tools: list[str] | None = None
    ) -> PromptReturn:
        future: asyncio.Future[PromptReturn] = asyncio.get_running_loop().create_future()
        try:
            self._pending_queue.put_nowait((prompt, allowed_tools, future))
        except asyncio.QueueFull as err:
            raise SessionBusyError("Session pending queue is full") from err

        if not self._active_turn:
            self._active_turn = True
            asyncio.create_task(self._consume_queue())

        return await future

    async def _consume_queue(self) -> None:
        try:
            while not self._pending_queue.empty():
                prompt, allowed_tools, future = self._pending_queue.get_nowait()
                self._cancel_requested = False
                try:
                    result = await self._run_turn(prompt, allowed_tools)
                    if not future.done():
                        future.set_result(result)
                except Exception as exc:
                    if not future.done():
                        future.set_exception(exc)
        finally:
            self._active_turn = False

    async def _run_turn(
        self, prompt: str | list[ContentBlock], allowed_tools: list[str] | None = None
    ) -> PromptReturn:
        self._turn_allowed_tools = allowed_tools

        # Inject memory before starting the turn
        if self.agent.memory is not None:
            self._memory_text = await self.agent.memory.recall()
        else:
            self._memory_text = None

        user_node = UserPromptNode(
            id=str(uuid.uuid4()),
            prev=self.tail,
            prompt=prompt,
        )
        self._append_node(user_node)

        partial_output = ""
        for _ in range(MAX_TURN_ITERATIONS):
            if self._cancel_requested:
                self._freeze_tail()
                return ("cancelled", partial_output)

            result = await self._generate_backend_result()

            match result.finish_reason:
                case "completed":
                    return await self._handle_completed(result)
                case "tool_call":
                    partial_output = await self._handle_tool_call(result, partial_output)
                case "cancelled":
                    self._freeze_tail()
                    await self._update_memory()
                    return ("cancelled", partial_output)
                case _:
                    raise RuntimeError(f"Unknown finish_reason: {result.finish_reason}")

        raise RuntimeError("Max turn iterations exceeded")

    async def _generate_backend_result(self) -> BackendTurnResult:
        """Generate a single backend turn result."""
        result: BackendTurnResult | None = None
        async for item in self.agent.backend.generate(self):
            if isinstance(item, BackendTurnResult):
                result = item
            else:
                await self.agent.client.update(self, item)

        if result is None:
            raise RuntimeError("Backend returned no result")
        return result

    async def _handle_completed(self, result: BackendTurnResult) -> PromptReturn:
        """Handle a completed turn result."""
        assistant_node = AssistantResponseNode(
            id=str(uuid.uuid4()),
            prev=self.tail,
            text=result.output_text,
        )
        self._append_node(assistant_node)
        self._freeze_tail()
        await self.agent.client.update(
            self,
            SessionUpdate(
                type="agent_message_chunk",
                data={"text": result.output_text},
            ),
        )
        await self._update_memory()
        return ("end_turn", result.output_text)

    async def _update_memory(self) -> None:
        """Update memory after a turn completes or is cancelled."""
        if self.agent.memory is not None:
            await self.agent.memory.remember(self)

    def _append_node(self, node: Node) -> None:
        if self.tail is not None:
            if hasattr(self.tail, "frozen") and not self.tail.frozen:
                self.tail.frozen = True
        self.tail = node

    def _freeze_tail(self) -> None:
        if self.tail is not None and hasattr(self.tail, "frozen"):
            self.tail.frozen = True

    async def cancel(self) -> None:
        if not self._active_turn:
            return
        self._cancel_requested = True

    async def fork(self) -> Session:
        if self._active_turn:
            raise RuntimeError("Cannot fork session with active turn")
        self._freeze_tail()
        new_session = SessionCore(
            session_id=str(uuid.uuid4()),
            cwd=self.cwd,
            agent=self.agent,
        )
        new_session.tail = self.tail
        return new_session

    async def compress(self) -> None:
        if self._active_turn:
            raise RuntimeError("Cannot compress session with active turn")
        if self.agent.compressor is None:
            raise RuntimeError("No compressor configured")
        new_head = await self.agent.compressor.compress(self.tail)
        self.tail = new_head

    def save(self) -> JSONValue:
        chain: list[dict[str, JSONValue]] = []
        node = self.tail
        while node is not None:
            chain.append(node.to_dict())
            node = node.prev
        chain.reverse()
        return {"id": self.id, "cwd": self.cwd, "chain": chain}  # type: ignore[dict-item]

    def _rebuild_tail(self, chain: list[Any]) -> None:
        """Rebuild tail from serialized chain data."""
        self.tail = _rebuild_chain(chain)

    async def _handle_tool_call(self, result: BackendTurnResult, partial_output: str) -> str:
        """Handle tool_call result and return updated partial_output."""
        partial_output = result.output_text or partial_output
        if result.output_text:
            await self.agent.client.update(
                self,
                SessionUpdate(
                    type="agent_message_chunk",
                    data={"text": result.output_text},
                ),
            )

        tool_call_node = self._create_tool_call_node(result)
        await self.agent.client.update(
            self,
            SessionUpdate(
                type="tool_call",
                data={"calls": tool_call_node.calls},  # type: ignore[dict-item]
            ),
        )

        tool_result_node = self._create_tool_result_node()
        await self._invoke_tools(result, tool_result_node)
        self._freeze_tail()

        return partial_output

    def _create_tool_call_node(self, result: BackendTurnResult) -> ToolCallNode:
        """Create and append a ToolCallNode."""
        node = ToolCallNode(
            id=str(uuid.uuid4()),
            prev=self.tail,
            calls={
                tc.call_id: {"tool_name": tc.tool_name, "arguments": tc.arguments}
                for tc in result.tool_calls
            },
        )
        self._append_node(node)
        return node

    def _create_tool_result_node(self) -> ToolResultNode:
        """Create and append a ToolResultNode."""
        node = ToolResultNode(
            id=str(uuid.uuid4()),
            prev=self.tail,
            results={},
        )
        self._append_node(node)
        return node

    def _check_tool_allowed(
        self,
        tc: BackendToolCall,
        allowed_names: set[str] | None,
        tool_result_node: ToolResultNode,
    ) -> bool:
        """Check if a tool call is allowed; return True if it should proceed."""
        if allowed_names is not None and tc.tool_name not in allowed_names:
            tool_result_node.results[tc.call_id] = {
                "status": "failed",
                "content": f"Tool not in allowed list: {tc.tool_name}",
            }
            return False

        if self.agent.permissions is not None:
            perm_action = self.agent.permissions.check(tc.tool_name)
            if perm_action == "deny":
                tool_result_node.results[tc.call_id] = {
                    "status": "failed",
                    "content": "Permission denied",
                }
                return False
            if perm_action == "ask":
                return True  # handled asynchronously by caller
        return True

    async def _invoke_tools(
        self, result: BackendTurnResult, tool_result_node: ToolResultNode
    ) -> None:
        """Invoke tools and populate tool_result_node."""
        from little_agent.agent.context import current_session

        allowed_names = (
            set(self._turn_allowed_tools) if self._turn_allowed_tools is not None else None
        )

        allowed_calls = []
        needs_permission: list[BackendToolCall] = []
        for tc in result.tool_calls:
            if not self._check_tool_allowed(tc, allowed_names, tool_result_node):
                continue
            if (
                self.agent.permissions is not None
                and self.agent.permissions.check(tc.tool_name) == "ask"
            ):
                needs_permission.append(tc)
                continue
            allowed_calls.append(tc)

        for tc in needs_permission:
            granted = await self.agent.client.request_permission(
                self,
                tc.tool_name,
                {"arguments": tc.arguments},
            )
            if granted:
                allowed_calls.append(tc)
            else:
                tool_result_node.results[tc.call_id] = {
                    "status": "failed",
                    "content": "Permission denied",
                }

        token = current_session.set(self)
        try:
            pending_calls = {tc.call_id: tc for tc in allowed_calls}
            tasks = [self.agent.tools.invoke(tc.tool_name, tc.arguments) for tc in allowed_calls]
            tool_results = await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            current_session.reset(token)

        for tc, res in zip(allowed_calls, tool_results, strict=True):
            if self._cancel_requested and tc.call_id in pending_calls:
                tool_result_node.results[tc.call_id] = {
                    "status": "cancelled",
                    "content": "",
                }
                del pending_calls[tc.call_id]
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
            await self.agent.client.update(
                self,
                SessionUpdate(
                    type="tool_call_update",
                    data={
                        "call_id": tc.call_id,
                        "status": tool_result_node.results[tc.call_id]["status"],
                        "content": tool_result_node.results[tc.call_id]["content"],
                    },
                ),
            )


class AgentCore(Agent):
    def __init__(
        self,
        client: Client,
        backend: Backend,
        tools: ToolProvider,
        compressor: Compressor | None = None,
        permissions: PermissionManager | None = None,
        memory: Any = None,
    ) -> None:
        self.client = client
        self.backend = backend
        self.tools = tools
        self.compressor = compressor
        self.permissions = permissions
        self.memory = memory

    async def new(self, cwd: str | None = None) -> Session:
        session = SessionCore(
            session_id=str(uuid.uuid4()),
            cwd=cwd,
            agent=self,
        )
        return session

    async def load(self, data: JSONValue) -> Session:
        if not isinstance(data, dict):
            raise ValueError("Invalid session data: expected dict")
        session_id = data.get("id")
        if not isinstance(session_id, str):
            raise ValueError("Session data missing 'id'")
        session_cwd = data.get("cwd")
        if session_cwd is not None and not isinstance(session_cwd, str):
            raise ValueError("Session 'cwd' must be a string or null")
        session = SessionCore(
            session_id=session_id,
            cwd=session_cwd,
            agent=self,
        )
        chain = data.get("chain", [])
        if isinstance(chain, list):
            session._rebuild_tail(chain)
        return session
