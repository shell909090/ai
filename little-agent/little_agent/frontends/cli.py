"""CLI frontend implementation."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from little_agent.backends.exceptions import BackendTimeoutError
from little_agent.types import JSONValue

from .protocol import Client, SessionUpdate

if TYPE_CHECKING:
    from little_agent.agent.protocol import Agent, Session

logger = logging.getLogger(__name__)

_SLASH_COMMANDS = [
    "/cancel",
    "/exit",
    "/fork",
    "/list-tools",
    "/load",
    "/new",
    "/quit",
    "/save",
]

_ChunkType = Literal["thinking", "agent"]


def _setup_readline() -> Path | None:
    """Configure readline history and tab completion. Returns history file path or None."""
    try:
        import readline

        history_file = Path.home() / ".little_agent_history"
        readline.set_history_length(1000)
        try:
            readline.read_history_file(str(history_file))
        except FileNotFoundError:
            pass

        def completer(text: str, state: int) -> str | None:
            options = [c for c in _SLASH_COMMANDS if c.startswith(text)]
            return options[state] if state < len(options) else None

        readline.set_completer_delims("")
        readline.set_completer(completer)
        readline.parse_and_bind("tab: complete")
        return history_file
    except ImportError:
        return None


class CliClient(Client):
    """CLI client implementation."""

    def __init__(self) -> None:
        self._updates: list[SessionUpdate] = []
        self._buffer_type: _ChunkType | None = None
        self._buffer_parts: list[str] = []

    def _flush_buffer(self) -> None:
        """Flush buffered content chunks as a single coalesced message."""
        if self._buffer_type is not None:
            text = "".join(self._buffer_parts).strip()
            if text:
                prefix = "Agent" if self._buffer_type == "agent" else "Thinking"
                print(f"[{prefix}] {text}")
        self._buffer_type = None
        self._buffer_parts = []

    def _print_tool_call(self, call_id: str, call_data: dict[str, Any]) -> None:
        """Print a tool call with truncated arguments."""
        tool_name = call_data.get("tool_name", "")
        arguments = call_data.get("arguments", {})
        kv_lines: list[str] = []
        for k, v in arguments.items():
            kv_lines.append(
                f"{k}: {v}" if isinstance(v, str) else f"{k}: {json.dumps(v, ensure_ascii=False)}"
            )
        lines = "\n".join(kv_lines).splitlines()
        if len(lines) > 5:
            args_text = "\n".join(lines[:5]) + f"\n...{len(lines) - 5} lines..."
        else:
            args_text = "\n".join(lines)
        print(f"[ToolCall] {call_id}: {tool_name}")
        if args_text:
            print(args_text)

    async def update(self, session: Session, update: SessionUpdate) -> None:
        """Handle session update with buffering for consecutive same-type chunks."""
        self._updates.append(update)
        if update.type in ("agent_message_chunk", "thinking_chunk"):
            chunk_type: _ChunkType = "agent" if update.type == "agent_message_chunk" else "thinking"
            text = str(update.data.get("text", ""))
            if chunk_type != self._buffer_type:
                self._flush_buffer()
                self._buffer_type = chunk_type
            if chunk_type == "agent" and text == "".join(self._buffer_parts):
                return
            self._buffer_parts.append(text)
        else:
            self._flush_buffer()
            if update.type == "tool_call":
                calls = update.data.get("calls", {})
                if not isinstance(calls, dict):
                    raise ValueError("tool_call update 'calls' must be a dict")
                for call_id, call_data in calls.items():
                    if not isinstance(call_data, dict):
                        raise ValueError(f"tool_call update call_data for {call_id} must be a dict")
                    self._print_tool_call(call_id, call_data)
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
        """Interactive permission prompt for CLI."""
        logger.debug("Permission request: kind=%s payload=%s", kind, payload)
        try:
            answer = await asyncio.to_thread(input, f"[Allow {kind}? y/N] ")
        except (EOFError, KeyboardInterrupt):
            return False
        return answer.strip().lower() in ("y", "yes")

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
            case ["/quit"] | ["/exit"]:
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
            case ["/list-tools"]:
                tools = agent.tools.desc_tool()
                if tools:
                    print("Available tools:")
                    for name, tooldef in tools.items():
                        print(f"  {name}: {tooldef.desc}")
                else:
                    print("No tools registered.")
                return session, True
            case _:
                print(f"Unknown command: {stripped}")
                return session, True

    async def _do_prompt(self, session: Session, user_input: str) -> None:
        """Send user input to the session and handle the result."""
        try:
            stop_reason, text = await session.prompt(user_input)
            self._flush_buffer()
            if stop_reason == "cancelled":
                print("[Cancelled]")
            else:
                logger.debug("Turn completed: %s", text)
        except BackendTimeoutError as e:
            self._flush_buffer()
            print(f"[Timeout] {e}")
        except Exception as e:
            self._flush_buffer()
            logger.exception("Error during prompt")
            print(f"[Error] {e}")

    async def run(self, agent: Agent) -> None:
        """Run the CLI interactive loop."""
        history_file = _setup_readline()
        session = await agent.new()
        print("Little Agent CLI. Commands: /new /save <path> /load <path> /cancel /fork /quit")
        try:
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

                await self._do_prompt(session, user_input)
        finally:
            if history_file is not None:
                try:
                    import readline

                    readline.write_history_file(str(history_file))
                except Exception:
                    pass
