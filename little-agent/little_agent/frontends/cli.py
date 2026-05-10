"""CLI frontend implementation."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
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


def _resolve_future(fut: asyncio.Future[str | None], text: str | None) -> None:
    """Set future result if not already done; used as call_soon_threadsafe callback."""
    if not fut.done():
        fut.set_result(text)


def _remove_last_history() -> None:
    """Remove the last readline history entry; no-op if readline is unavailable."""
    try:
        import readline as _rl

        _rl.remove_history_item(_rl.get_current_history_length() - 1)
    except (ImportError, ValueError):
        pass


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
        self._buffer_type: _ChunkType | None = None
        self._buffer_parts: list[str] = []
        # Bounded to prevent unbounded growth if asyncio.to_thread is mistakenly
        # mocked to return immediately in tests, which would otherwise let the
        # _stdin_reader busy-loop and OOM the host.
        self._stdin_queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=32)
        # Set means "no permission request in flight"; cleared while request_permission
        # is waiting on the queue, so _watch_cancel_loop backs off and does not race.
        self._permission_done: asyncio.Event = asyncio.Event()
        self._permission_done.set()

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

    async def _stdin_reader(self) -> None:
        """Background task reading stdin lines into _stdin_queue; None signals EOF."""
        loop = asyncio.get_running_loop()
        try:
            while True:
                fut: asyncio.Future[str | None] = loop.create_future()

                def _read(f: asyncio.Future[str | None] = fut) -> None:
                    try:
                        text: str | None = input("> ")
                    except (EOFError, KeyboardInterrupt):
                        text = None
                    try:
                        loop.call_soon_threadsafe(_resolve_future, f, text)
                    except RuntimeError:
                        pass  # event loop already closed

                # daemon=True: process can exit cleanly without waiting for this thread.
                # asyncio.to_thread uses the default ThreadPoolExecutor, which
                # asyncio.run() waits for via shutdown_default_executor() — that blocks
                # on Ctrl+C because the stdin thread never returns.
                threading.Thread(target=_read, daemon=True).start()
                result = await fut

                if result is None:
                    await self._stdin_queue.put(None)
                    break
                await self._stdin_queue.put(result)
                # Yield before starting the next thread so pending cancellation
                # is injected here rather than after a new thread launches.
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            pass

    async def request_permission(
        self,
        session: Session,
        kind: str,
        payload: dict[str, JSONValue],
    ) -> bool:
        """Interactive permission prompt for CLI."""
        logger.debug("Permission request: kind=%s payload=%s", kind, payload)
        print(f"[Allow {kind}? y/N] ", end="", flush=True)
        self._permission_done.clear()
        try:
            item = await self._stdin_queue.get()
        except asyncio.CancelledError:
            return False
        finally:
            self._permission_done.set()
        if item is None:
            return False
        stripped = item.strip()
        if stripped == "/cancel":
            await session.cancel()
            return False
        return stripped.lower() in ("y", "yes")

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

    async def _do_load(self, agent: Agent, session: Session, path: Path) -> tuple[Session, bool]:
        """Load session from file. Returns (session, success)."""
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            new_session = await agent.load(data)
            print(f"Session loaded from {path}")
            return new_session, True
        except Exception as e:
            logger.exception("Error loading session")
            print(f"[Error] {e}")
            return session, False

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
                session, ok = await self._do_load(agent, session, Path(path_str))
                if not ok:
                    print("[Load failed] Session unchanged.")
                return session, True
            case ["/list-tools"]:
                self._print_tools(agent)
                return session, True
            case _:
                print(f"Unknown command: {stripped}")
                return session, True

    def _print_tools(self, agent: Agent) -> None:
        """Print all registered tools."""
        tools = agent.tools.desc_tool()
        if tools:
            print("Available tools:")
            for name, tooldef in tools.items():
                print(f"  {name}: {tooldef.desc}")
        else:
            print("No tools registered.")

    async def _wait_for_permission(self, prompt_task: asyncio.Task[tuple[str, str]]) -> None:
        """Wait until _permission_done is set or prompt_task finishes."""
        perm_wait: asyncio.Task[bool] = asyncio.create_task(self._permission_done.wait())
        await asyncio.wait({prompt_task, perm_wait}, return_when=asyncio.FIRST_COMPLETED)
        if not perm_wait.done():
            perm_wait.cancel()
            try:
                await perm_wait
            except asyncio.CancelledError:
                pass

    async def _watch_cancel_loop(
        self, prompt_task: asyncio.Task[tuple[str, str]], session: Session
    ) -> None:
        """Watch _stdin_queue for /cancel and EOF while prompt_task runs.

        Any other input is put back on the queue for run() to handle after the prompt.
        """
        pending_get: asyncio.Task[str | None] | None = None
        try:
            while not prompt_task.done():
                if not self._permission_done.is_set():
                    await self._wait_for_permission(prompt_task)
                    continue
                if pending_get is None:
                    pending_get = asyncio.create_task(self._stdin_queue.get())
                done, _ = await asyncio.wait(
                    {prompt_task, pending_get}, return_when=asyncio.FIRST_COMPLETED
                )
                if pending_get not in done:
                    break  # prompt finished; pending_get still waiting
                item = pending_get.result()
                pending_get = None
                if item is None:
                    await self._stdin_queue.put(None)  # forward EOF to run()
                    break
                if item.strip() == "/cancel":
                    await session.cancel()
                    break
                # anything else (text, slash commands): put back for run()
                await self._stdin_queue.put(item)
                break
        finally:
            if pending_get is not None and not pending_get.done():
                pending_get.cancel()
                try:
                    await pending_get
                except asyncio.CancelledError:
                    pass

    async def _do_prompt(self, session: Session, user_input: str) -> None:
        """Send user input to session; watch for /cancel and queue text concurrently."""
        prompt_task: asyncio.Task[tuple[str, str]] = asyncio.create_task(session.prompt(user_input))
        try:
            await self._watch_cancel_loop(prompt_task, session)
            stop_reason, text = await prompt_task
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
        finally:
            if not prompt_task.done():
                prompt_task.cancel()
                try:
                    await prompt_task
                except (asyncio.CancelledError, Exception):
                    pass

    async def run(self, agent: Agent) -> None:
        """Run the CLI interactive loop."""
        history_file = _setup_readline()
        session = await agent.new()
        print("Little Agent CLI. Commands: /new /save <path> /load <path> /cancel /fork /quit")
        reader_task = asyncio.create_task(self._stdin_reader())
        try:
            while True:
                try:
                    user_input = await self._stdin_queue.get()
                except asyncio.CancelledError:
                    print("\nGoodbye!")
                    break

                if user_input is None:  # EOF
                    print("\nGoodbye!")
                    break

                stripped = user_input.strip()
                if not stripped:
                    continue

                if stripped.startswith("/"):
                    _remove_last_history()
                    session, should_continue = await self._handle_command(agent, session, stripped)
                    if not should_continue:
                        break
                    continue

                await self._do_prompt(session, user_input)
        finally:
            reader_task.cancel()
            try:
                await reader_task
            except asyncio.CancelledError:
                pass
            if history_file is not None:
                try:
                    import readline

                    readline.write_history_file(str(history_file))
                except Exception:
                    pass
