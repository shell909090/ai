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

_DANGEROUS_ENV_VARS = frozenset({"PATH"})
_DANGEROUS_ENV_PREFIXES = ("LD_", "DYLD_", "PYTHON")


class BashToolProvider:
    """Execute shell commands via asyncio subprocess."""

    def __init__(self, timeout: int = 30, max_timeout: int = 1800) -> None:
        self._timeout = timeout
        self._max_timeout = max_timeout
        self._tool_def = ToolDef(
            desc="Execute a shell command and return stdout/stderr",
            args=[
                ToolArgDef("command", "string", "The shell command to execute", True),
                ToolArgDef("cwd", "string", "Working directory for the command", False),
                ToolArgDef(
                    "env", "object", "Additional environment variables as key-value pairs", False
                ),
                ToolArgDef("stdin", "string", "Standard input to pass to the command", False),
                ToolArgDef("timeout", "integer", "Override default timeout in seconds", False),
            ],
        )

    async def _handle_timeout(
        self,
        proc: asyncio.subprocess.Process,
        command: str,
        timed_out: bool,
        exc: BaseException,
        effective_timeout: int,
    ) -> JSONValue:
        """Kill process after timeout or cancellation and return result."""
        if timed_out:
            logger.warning("bash: command timed out after %ss: %r", effective_timeout, command)
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, OSError) as e:
            logger.error("bash: failed to kill process: %s", e)
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except (TimeoutError, asyncio.CancelledError):
            pass
        if not timed_out:
            raise exc
        return {
            "stdout": "",
            "stderr": f"Command timed out after {effective_timeout} seconds",
            "returncode": -1,
        }

    def __iter__(self) -> Iterator[tuple[str, ToolDef, AsyncToolFn]]:
        """Yield the single bash tool triple."""
        yield ("bash", self._tool_def, self._dispatch)

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
                if key in _DANGEROUS_ENV_VARS or any(
                    key.startswith(p) for p in _DANGEROUS_ENV_PREFIXES
                ):
                    logger.warning("Blocked dangerous env var override: %r", key)
                else:
                    env[key] = str(v)

        stdin_val = args.get("stdin")
        if stdin_val is not None and not isinstance(stdin_val, str):
            raise ValueError("stdin must be a string")
        stdin_bytes: bytes | None = (
            stdin_val.encode("utf-8") if isinstance(stdin_val, str) else None
        )

        # Resolve per-call timeout (clamped to max_timeout).
        timeout_val = args.get("timeout")
        if timeout_val is not None and isinstance(timeout_val, (int, float)):
            requested = int(timeout_val)
            if requested > self._max_timeout:
                logger.warning(
                    "bash: requested timeout %ds exceeds max_timeout %ds; clamping",
                    requested,
                    self._max_timeout,
                )
                effective_timeout = self._max_timeout
            else:
                effective_timeout = max(1, requested)
        else:
            effective_timeout = self._timeout

        logger.debug("bash: command=%r cwd=%r timeout=%ds", command, cwd, effective_timeout)

        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE if stdin_bytes is not None else None,
            cwd=cwd,
            env=env,
            start_new_session=True,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=stdin_bytes), timeout=effective_timeout
            )
        except (TimeoutError, asyncio.CancelledError) as exc:
            return await self._handle_timeout(
                proc, command, isinstance(exc, TimeoutError), exc, effective_timeout
            )

        returncode = proc.returncode
        if returncode != 0:
            logger.warning("bash: command exited with returncode=%d: %r", returncode, command)
        return {
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
            "returncode": returncode,
        }
