"""Built-in bash tool provider."""

from __future__ import annotations

import asyncio

from little_agent.types import JSONValue

from .protocol import ToolMap, ToolProvider


class BashToolProvider(ToolProvider):
    """Execute shell commands via asyncio subprocess."""

    _TOOLS: ToolMap = {
        "bash": (
            "Execute a shell command and return stdout/stderr",
            [
                ("command", "string", "The shell command to execute", True),
            ],
        ),
    }
    _TIMEOUT = 30

    def list(self) -> ToolMap:
        """Return built-in tools."""
        return self._TOOLS.copy()

    async def invoke(self, name: str, **kwargs: JSONValue) -> JSONValue:
        """Invoke a built-in tool."""
        if name != "bash":
            raise ValueError(f"Unknown tool: {name}")
        command = kwargs.get("command", "")
        if not isinstance(command, str):
            raise ValueError("command must be a string")

        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self._TIMEOUT)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return f"Command timed out after {self._TIMEOUT} seconds"

        output = stdout.decode("utf-8", errors="replace")
        if stderr:
            output += "\n" + stderr.decode("utf-8", errors="replace")
        return output
