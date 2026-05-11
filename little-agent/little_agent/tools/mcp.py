"""MCP stdio transport provider."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from typing import Any

from little_agent.tools.protocol import AsyncToolFn, ToolArgDef, ToolDef
from little_agent.types import JSONValue

logger = logging.getLogger(__name__)

# MCP tool name regex allowed by Anthropic/OpenAI
_TOOL_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

_SCALAR_TYPES = {"string", "integer", "number", "boolean"}


class MCPStdioProvider:
    """Runs an MCP server as a subprocess and exposes its tools via stdio JSON-RPC."""

    def __init__(
        self,
        name: str,
        command: list[str],
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> None:
        """Initialize provider. Call start() to connect to the subprocess."""
        self._name = name
        self._command = command
        self._env = env or {}
        self._cwd = cwd
        self._tools: list[tuple[str, ToolDef, str]] = []
        self._running = False

    async def start(self) -> None:
        """Spawn subprocess, complete MCP initialize handshake, cache tools/list."""
        from mcp import ClientSession, StdioServerParameters, stdio_client

        server_params = StdioServerParameters(
            command=self._command[0],
            args=self._command[1:],
            env=self._env if self._env else None,
        )

        # The stdio_client is an async context manager; keep it alive for the lifetime
        self._cm = stdio_client(server_params)
        read, write = await self._cm.__aenter__()

        self._session = ClientSession(read, write)
        await self._session.__aenter__()

        # Initialize
        await self._session.initialize()

        # List tools
        tools_result = await self._session.list_tools()
        self._running = True

        for tool in tools_result.tools:
            namespaced_name = f"{self._name}__{tool.name}"

            # Validate name
            if not _TOOL_NAME_RE.match(namespaced_name):
                logger.warning(
                    "MCP server '%s': tool '%s' produces invalid namespaced name '%s'; skipping",
                    self._name,
                    tool.name,
                    namespaced_name,
                )
                continue

            # Convert inputSchema to ToolDef
            tooldef = self._convert_schema(tool.name, tool.description or "", tool.inputSchema)
            if tooldef is None:
                continue  # warning already logged

            self._tools.append((namespaced_name, tooldef, tool.name))

    def _convert_schema(self, tool_name: str, desc: str, schema: Any) -> ToolDef | None:
        """Convert MCP inputSchema to ToolDef. Returns None if schema is unsupported."""
        if not isinstance(schema, dict):
            logger.warning(
                "MCP server '%s': tool '%s' has no inputSchema; treating as no args",
                self._name,
                tool_name,
            )
            return ToolDef(desc=desc)

        if schema.get("type") != "object":
            logger.warning(
                "MCP server '%s': tool '%s' inputSchema top-level type is not 'object';"
                " skipping tool",
                self._name,
                tool_name,
            )
            return None

        properties = schema.get("properties", {})
        required_fields = set(schema.get("required", []))

        args: list[ToolArgDef] = []
        for field_name, field_schema in properties.items():
            if not isinstance(field_schema, dict):
                continue
            field_type = field_schema.get("type", "string")
            if field_type not in _SCALAR_TYPES:
                logger.warning(
                    "MCP server '%s': tool '%s' field '%s' has unsupported type '%s';"
                    " skipping tool",
                    self._name,
                    tool_name,
                    field_name,
                    field_type,
                )
                return None
            field_desc = field_schema.get("description", "")
            args.append(
                ToolArgDef(
                    name=field_name,
                    type=field_type,
                    desc=field_desc,
                    required=field_name in required_fields,
                )
            )

        return ToolDef(desc=desc, args=args)

    async def stop(self) -> None:
        """Terminate the MCP subprocess and clean up."""
        if not self._running:
            return
        self._running = False
        try:
            if hasattr(self, "_session"):
                await self._session.__aexit__(None, None, None)
        except BaseException:
            logger.debug("MCP session cleanup error for '%s'", self._name)
        try:
            if hasattr(self, "_cm"):
                await self._cm.__aexit__(None, None, None)
        except BaseException:
            logger.debug("MCP subprocess cleanup error for '%s'", self._name)

    def __iter__(self) -> Iterator[tuple[str, ToolDef, AsyncToolFn]]:
        """Yield (namespaced_name, tooldef, fn) for each MCP tool."""
        for namespaced_name, tooldef, original_name in self._tools:

            async def _call(
                args: dict[str, JSONValue], _name: str = original_name
            ) -> JSONValue:
                if not self._running:
                    raise RuntimeError(f"MCP server '{self._name}' is not running")
                try:
                    result = await self._session.call_tool(_name, args)
                    # Extract text content from result
                    content = result.content
                    if content and hasattr(content[0], "text"):
                        return content[0].text
                    return str(content) if content else ""
                except Exception as e:
                    raise RuntimeError(f"MCP tool call failed: {e}") from e

            yield namespaced_name, tooldef, _call
