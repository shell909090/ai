"""Built-in bash tool provider."""

from __future__ import annotations

import asyncio
import os
import signal

from little_agent.types import JSONValue

from .protocol import ToolMap, ToolProvider


class BashToolProvider(ToolProvider):
    """Execute shell commands via asyncio subprocess."""

    _TOOLS: ToolMap = {
        "bash": (
            "Execute a shell command and return stdout/stderr",
            [
                ("command", "string", "The shell command to execute", True),
                ("cwd", "string", "Working directory for the command", False),
                ("env", "object", "Additional environment variables as key-value pairs", False),
                ("stdin", "string", "Standard input to pass to the command", False),
            ],
        ),
    }
    _TIMEOUT = 30

    def list(self) -> ToolMap:
        """Return built-in tools."""
        return self._TOOLS.copy()

    async def invoke(self, name: str, kwargs: dict[str, JSONValue]) -> JSONValue:
        """Dispatch tool calls to the corresponding method."""
        if name != "bash":
            raise ValueError(f"Unknown tool: {name}")
        return await self.bash(**kwargs)

    async def bash(self, **kwargs: JSONValue) -> JSONValue:
        """Execute a shell command and return stdout/stderr."""
        command = kwargs.get("command", "")
        if not isinstance(command, str):
            raise ValueError("command must be a string")

        cwd_val = kwargs.get("cwd")
        cwd = cwd_val if isinstance(cwd_val, str) else None

        env_val = kwargs.get("env")
        env: dict[str, str] | None = None
        if isinstance(env_val, dict):
            env = {**os.environ, **{str(k): str(v) for k, v in env_val.items()}}

        stdin_val = kwargs.get("stdin")
        stdin_bytes: bytes | None = (
            stdin_val.encode("utf-8") if isinstance(stdin_val, str) else None
        )

        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE if stdin_bytes is not None else None,
            cwd=cwd,
            env=env,
            start_new_session=True,
        )
        timed_out = False
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=stdin_bytes), timeout=self._TIMEOUT
            )
        except (TimeoutError, asyncio.CancelledError) as exc:
            timed_out = isinstance(exc, TimeoutError)
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass
            # Drain without raising so the transport cleans up properly.
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except (TimeoutError, asyncio.CancelledError):
                pass
            if not timed_out:
                raise
            return f"Command timed out after {self._TIMEOUT} seconds"

        output = stdout.decode("utf-8", errors="replace")
        if stderr:
            output += "\n" + stderr.decode("utf-8", errors="replace")
        return output
