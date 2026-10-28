#!/usr/bin/env python3
"""Minimal MCP server for testing MCPStdioProvider."""

from __future__ import annotations

import asyncio
from typing import Any

from mcp import types
from mcp.server import Server
from mcp.server.lowlevel.server import ServerRequestContext
from mcp.server.stdio import stdio_server


async def list_tools(
    ctx: ServerRequestContext[Any], params: types.PaginatedRequestParams | None
) -> types.ListToolsResult:
    """Return the available test tools."""
    return types.ListToolsResult(
        tools=[
            types.Tool(
                name="echo",
                description="Echo text back",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Text to echo"},
                    },
                    "required": ["text"],
                },
            ),
            types.Tool(
                name="add",
                description="Add two numbers",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "a": {"type": "number", "description": "First number"},
                        "b": {"type": "number", "description": "Second number"},
                    },
                    "required": ["a", "b"],
                },
            ),
        ]
    )


async def call_tool(
    ctx: ServerRequestContext[Any], params: types.CallToolRequestParams
) -> types.CallToolResult:
    """Handle tool calls."""
    name, arguments = params.name, params.arguments or {}
    if name == "echo":
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=arguments.get("text", ""))]
        )
    elif name == "add":
        result = float(arguments.get("a", 0)) + float(arguments.get("b", 0))
        return types.CallToolResult(content=[types.TextContent(type="text", text=str(result))])
    raise ValueError(f"Unknown tool: {name}")


server = Server("test-server", on_list_tools=list_tools, on_call_tool=call_tool)


async def main() -> None:
    """Run the MCP server over stdio."""
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
