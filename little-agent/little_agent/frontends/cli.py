"""CLI frontend implementation."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
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
            if not isinstance(calls, dict):
                raise ValueError("tool_call update 'calls' must be a dict")
            for call_id, call_data in calls.items():
                if not isinstance(call_data, dict):
                    raise ValueError(f"tool_call update call_data for {call_id} must be a dict")
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

    async def _do_save(self, session: Session, path: Path) -> None:
        """Save session to file."""
        try:
            data = session.save()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            print(f"Session saved to {path}")
        except Exception as e:
            logger.exception("Error saving session")
            print(f"[Error] {e}")

    async def _do_load(self, agent: Agent, session: Session, path: Path) -> Session:
        """Load session from file."""
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            session = await agent.load(data)
            print(f"Session loaded from {path}")
        except Exception as e:
            logger.exception("Error loading session")
            print(f"[Error] {e}")
        return session

    async def _handle_command(
        self, agent: Agent, session: Session, stripped: str
    ) -> tuple[Session, bool]:
        """Handle CLI commands. Returns (session, should_continue)."""
        match stripped.split(" ", 1):
            case ["/quit"]:
                print("Goodbye!")
                return session, False
            case ["/cancel"]:
                await session.cancel()
                return session, True
            case ["/fork"]:
                session = await session.fork()
                print("Forked new session.")
                return session, True
            case ["/new"]:
                session = await agent.new()
                print("Created new session.")
                return session, True
            case ["/save", path_str]:
                await self._do_save(session, Path(path_str))
                return session, True
            case ["/load", path_str]:
                session = await self._do_load(agent, session, Path(path_str))
                return session, True
            case _:
                print(f"Unknown command: {stripped}")
                return session, True

    async def run(self, agent: Agent) -> None:
        """Run the CLI interactive loop."""
        session = await agent.new()
        print("Little Agent CLI. Commands: /new /save <path> /load <path> /cancel /fork /quit")
        while True:
            try:
                user_input = await asyncio.to_thread(input, "> ")
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye!")
                break

            stripped = user_input.strip()
            if not stripped:
                continue

            if stripped.startswith("/"):
                session, should_continue = await self._handle_command(agent, session, stripped)
                if not should_continue:
                    break
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
