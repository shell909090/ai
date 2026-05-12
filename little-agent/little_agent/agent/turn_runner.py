"""TurnRunner: per-turn execution pipeline."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING

from little_agent.backends.exceptions import ContextOverflowError
from little_agent.backends.protocol import BackendTurnResult
from little_agent.types import ContentBlock, PromptReturn, SessionUpdate

from .nodes import AssistantResponseNode, UserPromptNode

if TYPE_CHECKING:
    from .session import SessionCore

logger = logging.getLogger(__name__)

MAX_TURN_ITERATIONS = 20


class TurnRunner:
    """Executes a single agent turn end-to-end.

    Instantiated once per turn. Owns turn-scoped state (overflow retry flag,
    partial output, last backend result) so SessionCore does not have to.
    """

    def __init__(self, session: SessionCore) -> None:
        self._session = session
        self._overflow_retried: bool = False
        self._partial_output: str = ""
        self._last_result: BackendTurnResult | None = None

    async def run(
        self,
        prompt: str | list[ContentBlock],
        allowed_tools: list[str] | None = None,
    ) -> PromptReturn:
        """Execute one turn including backend/tool iterations and post-turn compress."""
        session = self._session
        session.turn_allowed_tools = allowed_tools

        await session.call_hooks("on_turn_start", session)

        user_node = UserPromptNode(
            id=str(uuid.uuid4()),
            prev=session.tail,
            prompt=prompt,
        )
        session.append_node(user_node)

        try:
            for _ in range(MAX_TURN_ITERATIONS):
                if session.is_cancel_requested:
                    assert session.tail is not None
                    session.tail.freeze()
                    await session.call_hooks("on_cancel", session)
                    return ("cancelled", self._partial_output)

                result, did_stream = await self._backend_result_with_retry()
                self._last_result = result

                match result.finish_reason:
                    case "completed":
                        return await self._handle_completed(result, did_stream)
                    case "tool_call":
                        self._partial_output = await self._handle_tool_call(result, did_stream)
                    case _:
                        raise RuntimeError(f"Unknown finish_reason: {result.finish_reason}")

            raise RuntimeError("Max turn iterations exceeded")
        finally:
            await session.call_hooks("on_turn_end", session)
            self._schedule_compress_if_needed()

    async def _backend_result_with_retry(self) -> tuple[BackendTurnResult, bool]:
        """Generate backend result; compress and retry once on ContextOverflowError."""
        session = self._session
        try:
            return await self._generate_backend_result()
        except ContextOverflowError:
            if self._overflow_retried or session.agent.compressor is None:
                raise
            logger.info("in-turn context overflow: compressing and retrying")
            old_tail = session.tail
            new_tail = await session.agent.compressor.compress(session.tail)
            if new_tail is None or new_tail is old_tail:
                logger.warning(
                    "in-turn compress was a no-op (too few turns to compress); "
                    "re-raising ContextOverflowError"
                )
                raise
            session.tail = new_tail
            await session.call_hooks("on_compress", session)
            self._overflow_retried = True
            return await self._generate_backend_result()

    async def _generate_backend_result(self) -> tuple[BackendTurnResult, bool]:
        """Generate a single backend turn result.

        Returns (result, did_stream) where did_stream is True when at least one
        ``agent_message_chunk`` SessionUpdate was forwarded to the client.
        """
        session = self._session
        result: BackendTurnResult | None = None
        did_stream: bool = False
        async for item in session.agent.backend.generate(session):
            if isinstance(item, BackendTurnResult):
                result = item
            else:
                if item.type == "agent_message_chunk":
                    did_stream = True
                await session.agent.client.update(session, item)

        if result is None:
            raise RuntimeError("Backend returned no result")
        return result, did_stream

    async def _handle_completed(self, result: BackendTurnResult, did_stream: bool) -> PromptReturn:
        """Handle a completed turn result.

        Only sends a full-text ``agent_message_chunk`` when *did_stream* is False,
        i.e. the backend did not already forward incremental chunks to the client.
        """
        session = self._session
        assistant_node = AssistantResponseNode(
            id=str(uuid.uuid4()),
            prev=session.tail,
            text=result.output_text,
            thinking=result.thinking_text or "",
        )
        session.append_node(assistant_node)
        assistant_node.freeze()
        if not did_stream:
            await session.agent.client.update(
                session,
                SessionUpdate(
                    type="agent_message_chunk",
                    data={"text": result.output_text},
                ),
            )
        return ("end_turn", result.output_text)

    async def _handle_tool_call(self, result: BackendTurnResult, did_stream: bool) -> str:
        """Delegate tool-call handling to ToolInvoker."""
        from .tool_invoker import ToolInvoker

        return await ToolInvoker(self._session).invoke(result, self._partial_output, did_stream)

    def _schedule_compress_if_needed(self) -> None:
        """Evaluate §2.6.2 trigger criteria; schedule post-turn compress if triggered."""
        session = self._session
        cw = session.agent.context_window
        compress_ratio = session.agent.compress_ratio

        metric: str
        ratio: float
        usage = self._last_result.usage if self._last_result is not None else None
        total_tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0) if usage else 0
        if total_tokens > 0:
            ratio = total_tokens / cw
            metric = f"tokens={total_tokens}"
        else:
            char_count = sum(
                len(str(node.to_dict()).encode("utf-8")) for node in session.iter_nodes()
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
        if session.agent.compressor is None:
            logger.warning(
                "compress would trigger (ratio=%.3f > R=%.2f) but no compressor configured",
                ratio,
                compress_ratio,
            )
            return
        session.compress_task = asyncio.create_task(self._run_post_turn_compress())

    async def _run_post_turn_compress(self) -> None:
        """Background task: compress history then resume the pending queue."""
        session = self._session
        try:
            new_tail = await session.agent.compressor.compress(session.tail)  # type: ignore[union-attr]
            if new_tail is not None:
                session.tail = new_tail
                await session.call_hooks("on_compress", session)
        except Exception:
            logger.exception("Post-turn compress failed")
        finally:
            session.on_post_turn_compress_done()
