"""CLI frontend implementation."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from little_agent.types import JSONValue

from .protocol import Client, SessionUpdate

if TYPE_CHECKING:
    from little_agent.agent.protocol import Agent, Session

logger = logging.getLogger(__name__)


class CliClient(Client):
    """CLI client implementation."""

    def __init__(self) -> None:
        self._updates: list[SessionUpdate] = []

    async def update(self, session: Session, update: SessionUpdate) -> None:
        """Handle session update."""
        self._updates.append(update)
        if update.type == "agent_message_chunk":
            text = update.data.get("text", "")
            print(f"[Agent] {text}")
        elif update.type == "tool_call":
            calls = update.data.get("calls", {})
            assert isinstance(calls, dict)
            for call_id, call_data in calls.items():
                assert isinstance(call_data, dict)
                print(f"[ToolCall] {call_id}: {call_data['tool_name']}")
        elif update.type == "tool_call_update":
            call_id_raw = update.data.get("call_id", "")
            status_raw = update.data.get("status", "")
            call_id = call_id_raw if isinstance(call_id_raw, str) else str(call_id_raw)
            status = status_raw if isinstance(status_raw, str) else str(status_raw)
            print(f"[ToolResult] {call_id}: {status}")

    async def request_permission(
        self,
        session: Session,
        kind: str,
        payload: dict[str, JSONValue],
    ) -> bool:
        """Always grant permission."""
        return True

    async def run(self, agent: Agent) -> None:
        """Run the CLI interactive loop."""
        session = await agent.new()
        print("Little Agent CLI. Type /quit to exit, /cancel to cancel current turn.")
        while True:
            try:
                user_input = await asyncio.to_thread(input, "> ")
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye!")
                break

            if not user_input.strip():
                continue

            if user_input.strip() == "/quit":
                print("Goodbye!")
                break

            if user_input.strip() == "/cancel":
                await session.cancel()
                continue

            if user_input.strip() == "/fork":
                session = await session.fork()
                print("Forked new session.")
                continue

            try:
                stop_reason, text = await session.prompt(user_input)
                if stop_reason == "cancelled":
                    print("[Cancelled]")
                else:
                    logger.debug("Turn completed: %s", text)
            except Exception as e:
                logger.exception("Error during prompt")
                print(f"[Error] {e}")
