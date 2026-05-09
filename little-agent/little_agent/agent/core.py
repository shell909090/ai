from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING, Any, Literal

from little_agent.backends.exceptions import ContextOverflowError
from little_agent.backends.protocol import BackendToolCall, BackendTurnResult
from little_agent.tools.protocol import ToolMap
from little_agent.types import ContentBlock, JSONValue, PromptReturn, SessionUpdate

from .exceptions import SessionBusyError
from .nodes import (
    AssistantResponseNode,
    Node,
    SummaryNode,
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
    from little_agent.tools.protocol import ToolRegistry

logger = logging.getLogger(__name__)

MAX_TURN_ITERATIONS = 20

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
        self._compress_task: asyncio.Task[None] | None = None

    def get_turn_tool_map(self) -> ToolMap:
        """Return tool map for current turn."""
        if self._turn_allowed_tools is None:
            return self.agent.tools.desc_tool()
        return self.agent.tools.desc_tool(set(self._turn_allowed_tools))

    async def prompt(
        self, prompt: str | list[ContentBlock], allowed_tools: list[str] | None = None
    ) -> PromptReturn:
        """Queue a user prompt and await the agent's response."""
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
        """Drain pending prompts serially; yield to compress task when scheduled."""
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
                # Post-turn compress was scheduled; it will restart the queue when done.
                if self._compress_task is not None:
                    return
        finally:
            if self._compress_task is None:
                self._active_turn = False

    async def _run_turn(
        self, prompt: str | list[ContentBlock], allowed_tools: list[str] | None = None
    ) -> PromptReturn:
        """Execute one user turn including all backend/tool iterations."""
        self._turn_allowed_tools = allowed_tools

        if self.agent.memory is not None:
            memory_text = await self.agent.memory.recall()
            if memory_text:
                mem_node = SummaryNode(
                    id=str(uuid.uuid4()),
                    prev=self.tail,
                    summary=memory_text,
                )
                self._append_node(mem_node)

        user_node = UserPromptNode(
            id=str(uuid.uuid4()),
            prev=self.tail,
            prompt=prompt,
        )
        self._append_node(user_node)

        partial_output = ""
        _overflow_retried = False
        last_result: BackendTurnResult | None = None
        try:
            for _ in range(MAX_TURN_ITERATIONS):
                if self._cancel_requested:
                    self._freeze_tail()
                    return ("cancelled", partial_output)

                result, _overflow_retried = await self._backend_result_with_retry(_overflow_retried)
                last_result = result

                match result.finish_reason:
                    case "completed":
                        return await self._handle_completed(result)
                    case "tool_call":
                        partial_output = await self._handle_tool_call(result, partial_output)
                    case "cancelled":
                        self._freeze_tail()
                        return ("cancelled", partial_output)
                    case _:
                        raise RuntimeError(f"Unknown finish_reason: {result.finish_reason}")

            raise RuntimeError("Max turn iterations exceeded")
        finally:
            await self._update_memory()
            self._schedule_compress_if_needed(last_result)

    def _schedule_compress_if_needed(self, last_result: BackendTurnResult | None) -> None:
        """Evaluate §7.6.2 trigger criteria; schedule post-turn compress if triggered."""
        if self.agent.compressor is None:
            return

        triggered = False
        use_token = False
        cw = self.agent.context_window
        compress_ratio = self.agent.compress_ratio

        if last_result is not None and last_result.usage is not None:
            usage = last_result.usage
            total_tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
            if total_tokens > 0:
                use_token = True
                ratio = total_tokens / cw
                triggered = ratio > compress_ratio
                logger.info(
                    "post-turn compress eval: tokens=%d ratio=%.3f R=%.2f triggered=%s",
                    total_tokens,
                    ratio,
                    compress_ratio,
                    triggered,
                )

        if not use_token:
            char_count = 0
            node: Node | None = self.tail
            while node is not None:
                char_count += len(str(node.to_dict()))
                node = node.prev
            ratio = (char_count / 4) / cw
            triggered = ratio > compress_ratio
            logger.info(
                "post-turn compress eval (char fallback): chars=%d ratio=%.3f R=%.2f triggered=%s",
                char_count,
                ratio,
                compress_ratio,
                triggered,
            )

        if triggered:
            self._compress_task = asyncio.create_task(self._run_post_turn_compress())

    async def _run_post_turn_compress(self) -> None:
        """Background task: compress history then resume the pending queue."""
        try:
            new_tail = await self.agent.compressor.compress(self.tail)  # type: ignore[union-attr]
            if new_tail is not None:
                self.tail = new_tail
        except Exception:
            logger.exception("Post-turn compress failed")
        finally:
            self._compress_task = None
            self._active_turn = False
            if not self._pending_queue.empty():
                self._active_turn = True
                asyncio.create_task(self._consume_queue())

    async def _backend_result_with_retry(
        self, overflow_retried: bool
    ) -> tuple[BackendTurnResult, bool]:
        """Generate backend result; compress and retry once on ContextOverflowError."""
        try:
            return await self._generate_backend_result(), overflow_retried
        except ContextOverflowError:
            if overflow_retried or self.agent.compressor is None:
                raise
            logger.info("in-turn context overflow: compressing and retrying")
            new_tail = await self.agent.compressor.compress(self.tail)
            if new_tail is not None:
                self.tail = new_tail
            return await self._generate_backend_result(), True

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
        # Only send full-text chunk if backend did not stream chunks.
        # Streaming backends already yield agent_message_chunk per token.
        # For mock backends that don't stream, still send the complete text.
        await self.agent.client.update(
            self,
            SessionUpdate(
                type="agent_message_chunk",
                data={"text": result.output_text},
            ),
        )
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
        """Cancel the active turn and any running post-turn compress."""
        if not self._active_turn:
            return
        self._cancel_requested = True
        if self._compress_task is not None:
            self._compress_task.cancel()

    async def fork(self) -> Session:
        """Fork into a new session sharing the frozen history."""
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
        """Manually compress session history (not allowed during an active turn)."""
        if self._active_turn:
            raise RuntimeError("Cannot compress session with active turn")
        if self.agent.compressor is None:
            raise RuntimeError("No compressor configured")
        new_head = await self.agent.compressor.compress(self.tail)
        self.tail = new_head

    def save(self) -> JSONValue:
        """Serialize session state to a JSON-compatible dict."""
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
        # Only send full-text chunk if backend did not stream chunks.
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
    ) -> Literal["allow", "deny", "ask"]:
        """Check if a tool call is allowed; return the permission action."""
        if allowed_names is not None and tc.tool_name not in allowed_names:
            tool_result_node.results[tc.call_id] = {
                "status": "failed",
                "content": f"Tool not in allowed list: {tc.tool_name}",
            }
            return "deny"

        if self.agent.permissions is not None:
            return self.agent.permissions.check(tc.tool_name)
        return "allow"

    async def _ask_permissions(
        self,
        needs_permission: list[BackendToolCall],
        tool_result_node: ToolResultNode,
    ) -> list[BackendToolCall]:
        """Request permission for 'ask' calls; return approved ones."""
        approved: list[BackendToolCall] = []
        for tc in needs_permission:
            granted = await self.agent.client.request_permission(
                self,
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
        """Invoke tools and populate tool_result_node."""
        from little_agent.agent.context import current_session

        allowed_names = (
            set(self._turn_allowed_tools) if self._turn_allowed_tools is not None else None
        )

        allowed_calls = []
        needs_permission: list[BackendToolCall] = []
        for tc in result.tool_calls:
            action = self._check_tool_allowed(tc, allowed_names, tool_result_node)
            if action == "deny":
                if tc.call_id not in tool_result_node.results:
                    tool_result_node.results[tc.call_id] = {
                        "status": "failed",
                        "content": "Permission denied",
                    }
                continue
            if action == "ask":
                needs_permission.append(tc)
                continue
            allowed_calls.append(tc)

        approved = await self._ask_permissions(needs_permission, tool_result_node)
        allowed_calls.extend(approved)

        token = current_session.set(self)
        try:
            pending_calls = {tc.call_id: tc for tc in allowed_calls}

            async def _call(name: str, args: dict[str, JSONValue]) -> JSONValue:
                return await self.agent.tools[name](args)

            tasks = [_call(tc.tool_name, tc.arguments) for tc in allowed_calls]
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
        tools: ToolRegistry,
        compressor: Compressor | None = None,
        permissions: PermissionManager | None = None,
        memory: Any = None,
        compress_ratio: float = 0.5,
        context_window: int = 128000,
    ) -> None:
        self.client = client
        self.backend = backend
        self.tools = tools
        self.compressor = compressor
        self.permissions = permissions
        self.memory = memory
        self.compress_ratio = compress_ratio
        self.context_window = context_window

    async def new(self, cwd: str | None = None) -> Session:
        """Create a new session."""
        session = SessionCore(
            session_id=str(uuid.uuid4()),
            cwd=cwd,
            agent=self,
        )
        return session

    async def load(self, data: JSONValue) -> Session:
        """Load a session from serialized data."""
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
