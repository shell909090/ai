"""SessionCore: per-conversation state and turn entry point."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from little_agent.tools.protocol import ToolMap
from little_agent.types import ContentBlock, JSONValue, Node, PromptReturn, Session

from .exceptions import SessionBusyError

if TYPE_CHECKING:
    from .agent import AgentCore

logger = logging.getLogger(__name__)

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
        self.system_prompt: str | None = None
        self.summaries: list[str] = []
        self.messages: list[Node] = []
        self.turn_allowed_tools: list[str] | None = None
        self._active_turn: bool = False
        self._cancel_requested: bool = False
        self._pending_queue: asyncio.Queue[_PendingItem] = asyncio.Queue(maxsize=3)
        self.compress_task: asyncio.Task[None] | None = None
        # Holds strong references to background tasks to prevent GC under Python 3.11+.
        self._bg_tasks: set[asyncio.Task[object]] = set()

    @property
    def is_cancel_requested(self) -> bool:
        """Return whether cancel has been requested for the active turn."""
        return self._cancel_requested

    async def call_hooks(self, method_name: str, *args: Any) -> None:
        """Call hook method on all hooks; catch and log exceptions, never propagate."""
        for hook in self.agent.hooks:
            try:
                await getattr(hook, method_name)(*args)
            except Exception:
                logger.exception(
                    "Hook %s.%s failed [session=%s]",
                    type(hook).__name__,
                    method_name,
                    self.id,
                )

    def get_turn_tool_map(self) -> ToolMap:
        """Return tool map for current turn."""
        if self.turn_allowed_tools is None:
            return self.agent.tools.desc_tool()
        return self.agent.tools.desc_tool(set(self.turn_allowed_tools))

    def iter_nodes(self) -> Iterator[Node]:
        """Iterate messages in reverse order (newest first)."""
        return reversed(self.messages)

    async def prompt(
        self, prompt: str | list[ContentBlock], allowed_tools: list[str] | None = None
    ) -> PromptReturn:
        """Queue a user prompt and await the agent's response."""
        future: asyncio.Future[PromptReturn] = asyncio.get_running_loop().create_future()
        try:
            self._pending_queue.put_nowait((prompt, allowed_tools, future))
        except asyncio.QueueFull as err:
            raise SessionBusyError("Session pending queue is full") from err

        # Safety: no await between this check and the assignment in
        # _start_consume_queue_task. asyncio cooperative scheduling ensures this
        # read-modify is atomic. Do NOT add any await before the dispatch.
        if not self._active_turn:
            self._start_consume_queue_task()

        return await future

    def _start_consume_queue_task(self) -> None:
        """Mark session active and dispatch a queue consumer task."""
        self._active_turn = True
        t = asyncio.create_task(self._consume_queue())
        self._bg_tasks.add(t)
        t.add_done_callback(self._bg_tasks.discard)

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

    def on_post_turn_compress_done(self) -> None:
        """Reset compress task state and resume pending queue if non-empty.

        Called by TurnRunner._run_post_turn_compress in its finally block.
        """
        self.compress_task = None
        self._active_turn = False
        if not self._pending_queue.empty():
            self._start_consume_queue_task()

    async def _run_turn(
        self, prompt: str | list[ContentBlock], allowed_tools: list[str] | None = None
    ) -> PromptReturn:
        """Execute one user turn including all backend/tool iterations."""
        from little_agent.agent.context import current_session_id, current_turn_id

        from .turn_runner import TurnRunner

        turn_id = str(uuid.uuid4())[:8]
        sid_token = current_session_id.set(self.id)
        tid_token = current_turn_id.set(turn_id)
        try:
            return await TurnRunner(self).run(prompt, allowed_tools)
        finally:
            current_session_id.reset(sid_token)
            current_turn_id.reset(tid_token)

    def append_node(self, node: Node) -> None:
        self.messages.append(node)

    def _apply_compress_result(self, summary: str, remaining: list[Node]) -> None:
        """Apply compressor output; trim old summaries per W-limit."""
        if summary:
            self.summaries.append(summary)
        self.messages = remaining
        w_tokens = self.agent.compressed_window_tokens
        if w_tokens > 0:
            while len(self.summaries) > 1:
                total = sum(len(s.encode("utf-8")) // 3 for s in self.summaries)
                if total <= w_tokens:
                    break
                self.summaries.pop(0)

    async def wait_compress(self) -> None:
        """Wait for any in-flight post-turn compress task to complete."""
        if self.compress_task is not None:
            await self.compress_task

    async def cancel(self) -> None:
        """Cancel the active turn and any running post-turn compress."""
        if not self._active_turn:
            return
        self._cancel_requested = True
        if self.compress_task is not None:
            self.compress_task.cancel()

    async def fork(self) -> Session:
        """Fork into a new session with a shallow copy of messages and summaries."""
        if self._active_turn:
            raise RuntimeError("Cannot fork session with active turn")
        new_session = SessionCore(
            session_id=str(uuid.uuid4()),
            cwd=self.cwd,
            agent=self.agent,
        )
        new_session.system_prompt = self.system_prompt
        new_session.summaries = list(self.summaries)
        new_session.messages = list(self.messages)
        await self.call_hooks("on_fork", self, new_session)
        return new_session

    async def compress(self) -> None:
        """Manually compress session history (not allowed during an active turn)."""
        if self._active_turn:
            raise RuntimeError("Cannot compress session with active turn")
        if self.agent.compressor is None:
            raise RuntimeError("No compressor configured")
        summary, remaining = await self.agent.compressor.compress(self.messages)
        self._apply_compress_result(summary, remaining)
        await self.call_hooks("on_compress", self)

    def save(self) -> JSONValue:
        """Serialize session state to a JSON-compatible dict."""
        return {
            "id": self.id,
            "cwd": self.cwd,
            "system_prompt": self.system_prompt,
            "summaries": self.summaries,  # type: ignore[dict-item]
            "messages": [node.to_dict() for node in self.messages],
        }
