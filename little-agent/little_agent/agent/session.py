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
        self.compress_task: asyncio.Task[None] | None = None
        # Holds strong references to background tasks to prevent GC under Python 3.11+.
        self._bg_tasks: set[asyncio.Task[object]] = set()

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

        # Safety: no await between this check and the assignment below.
        # asyncio cooperative scheduling ensures this read-modify is atomic.
        # Do NOT add any await between these two lines.
        if not self._active_turn:
            self._active_turn = True
            t = asyncio.create_task(self._consume_queue())
            self._bg_tasks.add(t)
            t.add_done_callback(self._bg_tasks.discard)

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
                if self.compress_task is not None:
                    return
        finally:
            if self.compress_task is None:
                self._active_turn = False

    async def _run_turn(
        self, prompt: str | list[ContentBlock], allowed_tools: list[str] | None = None
    ) -> PromptReturn:
        """Execute one user turn including all backend/tool iterations."""
        from little_agent.agent.context import current_session_id, current_turn_id

        turn_id = str(uuid.uuid4())[:8]
        sid_token = current_session_id.set(self.id)
        tid_token = current_turn_id.set(turn_id)
        try:
            return await self._run_turn_inner(prompt, allowed_tools)
        finally:
            current_session_id.reset(sid_token)
            current_turn_id.reset(tid_token)

    async def _run_turn_inner(
        self, prompt: str | list[ContentBlock], allowed_tools: list[str] | None = None
    ) -> PromptReturn:
        """Inner turn execution after context vars are set."""
        self._turn_allowed_tools = allowed_tools

        user_node = UserPromptNode(
            id=str(uuid.uuid4()),
            prev=self.tail,
            prompt=prompt,
        )
        self.append_node(user_node)

        partial_output = ""
        _overflow_retried = False
        last_result: BackendTurnResult | None = None
        try:
            for _ in range(MAX_TURN_ITERATIONS):
                if self._cancel_requested:
                    assert self.tail is not None
                    self.tail.freeze()
                    return ("cancelled", partial_output)

                result, did_stream, _overflow_retried = await self._backend_result_with_retry(
                    _overflow_retried
                )
                last_result = result

                match result.finish_reason:
                    case "completed":
                        return await self._handle_completed(result, did_stream)
                    case "tool_call":
                        partial_output = await self._handle_tool_call(
                            result, partial_output, did_stream
                        )
                    case _:
                        raise RuntimeError(f"Unknown finish_reason: {result.finish_reason}")

            raise RuntimeError("Max turn iterations exceeded")
        finally:
            for _logger in self.agent.loggers:
                try:
                    await _logger.log(self)
                except Exception:
                    logger.exception("Logger %s failed", _logger)
            self._schedule_compress_if_needed(last_result)

    def _iter_nodes(self) -> Iterator["Node"]:
        node: Node | None = self.tail
        while node is not None:
            yield node
            node = node.prev

    def _schedule_compress_if_needed(self, last_result: BackendTurnResult | None) -> None:
        """Evaluate §7.6.2 trigger criteria; schedule post-turn compress if triggered."""
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
            char_count = sum(
                len(str(node.to_dict()).encode("utf-8")) for node in self._iter_nodes()
            )
            ratio = (char_count / 3) / cw
            metric = f"chars={char_count} (fallback)"

        triggered = ratio > compress_ratio
        logger.info(
            "post-turn compress eval: %s ratio=%.3f R=%.2f triggered=%s",
            metric,
            ratio,
            compress_ratio,
            triggered,
        )

        if not triggered:
            return
        if self.agent.compressor is None:
            logger.warning(
                "compress would trigger (ratio=%.3f > R=%.2f) but no compressor configured",
                ratio,
                compress_ratio,
            )
            return
        self.compress_task = asyncio.create_task(self._run_post_turn_compress())

    async def _run_post_turn_compress(self) -> None:
        """Background task: compress history then resume the pending queue."""
        try:
            new_tail = await self.agent.compressor.compress(self.tail)  # type: ignore[union-attr]
            if new_tail is not None:
                self.tail = new_tail
        except Exception:
            logger.exception("Post-turn compress failed")
        finally:
            self.compress_task = None
            self._active_turn = False
            if not self._pending_queue.empty():
                self._active_turn = True
                t = asyncio.create_task(self._consume_queue())
                self._bg_tasks.add(t)
                t.add_done_callback(self._bg_tasks.discard)

    async def _backend_result_with_retry(
        self, overflow_retried: bool
    ) -> tuple[BackendTurnResult, bool, bool]:
        """Generate backend result; compress and retry once on ContextOverflowError.

        Returns (result, did_stream, overflow_retried).
        """
        try:
            result, did_stream = await self._generate_backend_result()
            return result, did_stream, overflow_retried
        except ContextOverflowError:
            if overflow_retried or self.agent.compressor is None:
                raise
            logger.info("in-turn context overflow: compressing and retrying")
            new_tail = await self.agent.compressor.compress(self.tail)
            if new_tail is not None:
                self.tail = new_tail
            result, did_stream = await self._generate_backend_result()
            return result, did_stream, True

    async def _generate_backend_result(self) -> tuple[BackendTurnResult, bool]:
        """Generate a single backend turn result.

        Returns (result, did_stream) where did_stream is True when at least one
        ``agent_message_chunk`` SessionUpdate was forwarded to the client.
        """
        result: BackendTurnResult | None = None
        did_stream: bool = False
        async for item in self.agent.backend.generate(self):
            if isinstance(item, BackendTurnResult):
                result = item
            else:
                if item.type == "agent_message_chunk":
                    did_stream = True
                await self.agent.client.update(self, item)

        if result is None:
            raise RuntimeError("Backend returned no result")
        return result, did_stream

    async def _handle_completed(self, result: BackendTurnResult, did_stream: bool) -> PromptReturn:
        """Handle a completed turn result.

        Only sends a full-text ``agent_message_chunk`` when *did_stream* is False,
        i.e. the backend did not already forward incremental chunks to the client.
        """
        assistant_node = AssistantResponseNode(
            id=str(uuid.uuid4()),
            prev=self.tail,
            text=result.output_text,
            thinking=result.thinking_text or "",
        )
        self.append_node(assistant_node)
        assistant_node.freeze()
        if not did_stream:
            await self.agent.client.update(
                self,
                SessionUpdate(
                    type="agent_message_chunk",
                    data={"text": result.output_text},
                ),
            )
        return ("end_turn", result.output_text)

    def append_node(self, node: Node) -> None:
        if self.tail is not None:
            self.tail.freeze()
        self.tail = node

    async def cancel(self) -> None:
        """Cancel the active turn and any running post-turn compress."""
        if not self._active_turn:
            return
        self._cancel_requested = True
        if self.compress_task is not None:
            self.compress_task.cancel()

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

    async def _handle_tool_call(
        self, result: BackendTurnResult, partial_output: str, did_stream: bool = False
    ) -> str:
        """Delegate tool-call handling to ToolInvoker."""
        from .tool_invoker import ToolInvoker

        return await ToolInvoker(self).invoke(result, partial_output, did_stream)
