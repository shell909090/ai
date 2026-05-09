"""SessionCore: per-conversation state and turn execution."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from little_agent.backends.exceptions import ContextOverflowError
from little_agent.backends.protocol import BackendTurnResult
from little_agent.tools.protocol import ToolMap
from little_agent.types import ContentBlock, JSONValue, PromptReturn, SessionUpdate

from .exceptions import SessionBusyError
from .nodes import (
    AssistantResponseNode,
    Node,
    SummaryNode,
    UserPromptNode,
    _rebuild_chain,
)
from .protocol import Session

if TYPE_CHECKING:
    from .agent import AgentCore

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
                    assert self.tail is not None
                    self.tail.freeze()
                    return ("cancelled", partial_output)

                result, _overflow_retried = await self._backend_result_with_retry(_overflow_retried)
                last_result = result

                match result.finish_reason:
                    case "completed":
                        return await self._handle_completed(result)
                    case "tool_call":
                        partial_output = await self._handle_tool_call(result, partial_output)
                    case "cancelled":
                        assert self.tail is not None
                        self.tail.freeze()
                        return ("cancelled", partial_output)
                    case _:
                        raise RuntimeError(f"Unknown finish_reason: {result.finish_reason}")

            raise RuntimeError("Max turn iterations exceeded")
        finally:
            await self._update_memory()
            self._schedule_compress_if_needed(last_result)

    def _iter_nodes(self) -> Iterator["Node"]:
        node: Node | None = self.tail
        while node is not None:
            yield node
            node = node.prev

    def _schedule_compress_if_needed(self, last_result: BackendTurnResult | None) -> None:
        """Evaluate §7.6.2 trigger criteria; schedule post-turn compress if triggered."""
        if self.agent.compressor is None:
            return

        cw = self.agent.context_window
        compress_ratio = self.agent.compress_ratio

        metric: str
        ratio: float
        usage = last_result.usage if last_result is not None else None
        total_tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0) if usage else 0
        if total_tokens > 0:
            ratio = total_tokens / cw
            metric = f"tokens={total_tokens}"
        else:
            char_count = sum(len(str(node.to_dict())) for node in self._iter_nodes())
            ratio = (char_count / 4) / cw
            metric = f"chars={char_count} (fallback)"

        triggered = ratio > compress_ratio
        logger.info(
            "post-turn compress eval: %s ratio=%.3f R=%.2f triggered=%s",
            metric,
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
        assistant_node.freeze()
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
            self.tail.freeze()
        self.tail = node

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
        if self.tail is not None:
            self.tail.freeze()
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
        """Delegate tool-call handling to ToolInvoker."""
        from .tool_invoker import ToolInvoker

        return await ToolInvoker(self).invoke(result, partial_output)
