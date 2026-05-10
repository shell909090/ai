"""Built-in bash tool provider."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from collections.abc import Iterator

from little_agent.types import JSONValue

from .protocol import AsyncToolFn, ToolArgDef, ToolDef

logger = logging.getLogger(__name__)

_DANGEROUS_ENV_VARS = frozenset(
    {
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "LD_AUDIT",
        "LD_DEBUG",
        "DYLD_INSERT_LIBRARIES",
        "DYLD_LIBRARY_PATH",
        "PATH",
        "PYTHONPATH",
        "PYTHONSTARTUP",
    }
)


class BashToolProvider:
    """Execute shell commands via asyncio subprocess."""

    _TOOL_DEF = ToolDef(
        desc="Execute a shell command and return stdout/stderr",
        args=[
            ToolArgDef("command", "string", "The shell command to execute", True),
            ToolArgDef("cwd", "string", "Working directory for the command", False),
            ToolArgDef(
                "env", "object", "Additional environment variables as key-value pairs", False
            ),
            ToolArgDef("stdin", "string", "Standard input to pass to the command", False),
        ],
    )
    _TIMEOUT = 30

    def __iter__(self) -> Iterator[tuple[str, ToolDef, AsyncToolFn]]:
        """Yield the single bash tool triple."""
        yield ("bash", self._TOOL_DEF, self._dispatch)

    async def _dispatch(self, args: dict[str, JSONValue]) -> JSONValue:
        """Execute a shell command and return stdout/stderr."""
        command = args.get("command", "")
        if not isinstance(command, str):
            raise ValueError("command must be a string")

        cwd_val = args.get("cwd")
        cwd = cwd_val if isinstance(cwd_val, str) else None

        env_val = args.get("env")
        env: dict[str, str] | None = None
        if isinstance(env_val, dict):
            env = {**os.environ}
            for k, v in env_val.items():
                key = str(k)
                if key in _DANGEROUS_ENV_VARS:
                    logger.warning("Blocked dangerous env var override: %r", key)
                else:
                    env[key] = str(v)

        stdin_val = args.get("stdin")
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
            return {
                "stdout": "",
                "stderr": f"Command timed out after {self._TIMEOUT} seconds",
                "returncode": -1,
            }

        return {
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
            "returncode": proc.returncode,
        }
