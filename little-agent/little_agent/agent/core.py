from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING, Any

from little_agent.frontends.protocol import SessionUpdate
from little_agent.types import ContentBlock, JSONValue, PromptReturn

from .exceptions import SessionBusyError
from .nodes import (
    AssistantResponseNode,
    Node,
    SummaryNode,
    ToolCallNode,
    ToolResultNode,
    UserPromptNode,
)
from .protocol import Agent, Compressor, Session

if TYPE_CHECKING:
    from little_agent.backends.protocol import Backend, BackendTurnResult
    from little_agent.frontends.protocol import Client
    from little_agent.tools.protocol import ToolManager

MAX_TURN_ITERATIONS = 10

_PendingItem = tuple[str | list[ContentBlock], asyncio.Future[PromptReturn]]


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

    async def prompt(self, prompt: str | list[ContentBlock]) -> PromptReturn:
        if self._active_turn:
            future: asyncio.Future[PromptReturn] = asyncio.get_running_loop().create_future()
            try:
                self._pending_queue.put_nowait((prompt, future))
            except asyncio.QueueFull as err:
                raise SessionBusyError("Session pending queue is full") from err
            return await future

        self._active_turn = True
        self._cancel_requested = False
        try:
            return await self._run_turn(prompt)
        finally:
            self._active_turn = False
            if not self._pending_queue.empty():
                next_prompt, next_future = self._pending_queue.get_nowait()
                asyncio.create_task(self._process_pending(next_prompt, next_future))

    async def _process_pending(
        self, prompt: str | list[ContentBlock], future: asyncio.Future[PromptReturn]
    ) -> None:
        self._active_turn = True
        self._cancel_requested = False
        try:
            result = await self._run_turn(prompt)
            future.set_result(result)
        except Exception as exc:
            future.set_exception(exc)
        finally:
            self._active_turn = False
            if not self._pending_queue.empty():
                next_prompt, next_future = self._pending_queue.get_nowait()
                asyncio.create_task(self._process_pending(next_prompt, next_future))

    async def _run_turn(self, prompt: str | list[ContentBlock]) -> PromptReturn:
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

            result = await self.agent.backend.generate(self)

            if result.finish_reason == "completed":
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
                return ("end_turn", result.output_text)

            if result.finish_reason == "tool_call":
                handler = _ToolCallHandler(self)
                partial_output = await handler.handle(result, partial_output)
                continue

            if result.finish_reason == "cancelled":
                self._freeze_tail()
                return ("cancelled", partial_output)

        raise RuntimeError("Max turn iterations exceeded")

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
            item: dict[str, JSONValue] = {"kind": node.kind, "id": node.id}
            if isinstance(node, UserPromptNode):
                prompt: JSONValue = node.prompt  # type: ignore[assignment]
                item["prompt"] = prompt
            elif isinstance(node, AssistantResponseNode):
                text = node.text
                item["text"] = text
            elif isinstance(node, ToolCallNode):
                calls: JSONValue = node.calls  # type: ignore[assignment]
                item["calls"] = calls
            elif isinstance(node, ToolResultNode):
                results: JSONValue = node.results  # type: ignore[assignment]
                item["results"] = results
            chain.append(item)
            node = node.prev
        chain.reverse()
        return {"id": self.id, "cwd": self.cwd, "chain": chain}  # type: ignore[dict-item]


class AgentCore(Agent):
    def __init__(
        self,
        client: Client,
        backend: Backend,
        tools: ToolManager,
        compressor: Compressor | None = None,
    ) -> None:
        self.client = client
        self.backend = backend
        self.tools = tools
        self.compressor = compressor

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
            session.tail = self._rebuild_chain(chain)
        return session

    def _rebuild_chain(self, chain: list[Any]) -> Node | None:
        """Rebuild node chain from serialized data."""
        if not chain:
            return None
        prev: Node | None = None
        for item in chain:
            prev = self._rebuild_node(item, prev)
        return prev

    def _rebuild_node(self, item: Any, prev: Node | None) -> Node:
        """Rebuild a single node from serialized data."""
        if not isinstance(item, dict):
            raise ValueError("Chain item must be a dict")
        kind = item.get("kind")
        node_id = item.get("id")
        if not isinstance(kind, str) or not isinstance(node_id, str):
            raise ValueError("Chain item must have 'kind' and 'id' as strings")
        if kind == "user_prompt":
            return self._build_user_prompt_node(item, node_id, prev)
        if kind == "assistant_response":
            return self._build_assistant_response_node(item, node_id, prev)
        if kind == "tool_call":
            return self._build_tool_call_node(item, node_id, prev)
        if kind == "tool_result":
            return self._build_tool_result_node(item, node_id, prev)
        if kind == "summary":
            return self._build_summary_node(item, node_id, prev)
        raise ValueError(f"Unknown node kind: {kind}")

    def _build_user_prompt_node(
        self, item: dict[str, Any], node_id: str, prev: Node | None
    ) -> Node:
        prompt = item.get("prompt", "")
        if not isinstance(prompt, (str, list)):
            raise ValueError("UserPromptNode 'prompt' must be a string or list")
        return UserPromptNode(id=node_id, prev=prev, prompt=prompt)

    def _build_assistant_response_node(
        self, item: dict[str, Any], node_id: str, prev: Node | None
    ) -> Node:
        text = item.get("text", "")
        if not isinstance(text, str):
            raise ValueError("AssistantResponseNode 'text' must be a string")
        return AssistantResponseNode(id=node_id, prev=prev, text=text, frozen=True)

    def _build_tool_call_node(self, item: dict[str, Any], node_id: str, prev: Node | None) -> Node:
        calls = item.get("calls", {})
        if not isinstance(calls, dict):
            raise ValueError("ToolCallNode 'calls' must be a dict")
        return ToolCallNode(id=node_id, prev=prev, calls=calls)

    def _build_tool_result_node(
        self, item: dict[str, Any], node_id: str, prev: Node | None
    ) -> Node:
        results = item.get("results", {})
        if not isinstance(results, dict):
            raise ValueError("ToolResultNode 'results' must be a dict")
        return ToolResultNode(id=node_id, prev=prev, results=results, frozen=True)

    def _build_summary_node(self, item: dict[str, Any], node_id: str, prev: Node | None) -> Node:
        summary = item.get("summary")
        return SummaryNode(id=node_id, prev=prev, summary=summary)


class _ToolCallHandler:
    """Handles tool_call finish_reason from backend."""

    def __init__(self, session: SessionCore) -> None:
        self.session = session

    async def handle(self, result: BackendTurnResult, partial_output: str) -> str:
        """Handle tool_call result and return updated partial_output."""
        partial_output = result.output_text or partial_output
        if result.output_text:
            await self.session.agent.client.update(
                self.session,
                SessionUpdate(
                    type="agent_message_chunk",
                    data={"text": result.output_text},
                ),
            )
        tool_call_node = ToolCallNode(
            id=str(uuid.uuid4()),
            prev=self.session.tail,
            calls={
                tc.call_id: {"tool_name": tc.tool_name, "arguments": tc.arguments}
                for tc in result.tool_calls
            },
        )
        self.session._append_node(tool_call_node)
        await self.session.agent.client.update(
            self.session,
            SessionUpdate(
                type="tool_call",
                data={"calls": tool_call_node.calls},  # type: ignore[dict-item]
            ),
        )

        tool_result_node = ToolResultNode(
            id=str(uuid.uuid4()),
            prev=self.session.tail,
            results={},
        )
        self.session._append_node(tool_result_node)
        self.session._freeze_tail()

        pending_calls = {tc.call_id: tc for tc in result.tool_calls}
        tasks = [
            self.session.agent.tools.invoke(tc.tool_name, **tc.arguments)
            for tc in result.tool_calls
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for tc, res in zip(result.tool_calls, results, strict=True):
            if self.session._cancel_requested and tc.call_id in pending_calls:
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
            await self.session.agent.client.update(
                self.session,
                SessionUpdate(
                    type="tool_call_update",
                    data={
                        "call_id": tc.call_id,
                        "status": tool_result_node.results[tc.call_id]["status"],
                        "content": tool_result_node.results[tc.call_id]["content"],
                    },
                ),
            )

        return partial_output
