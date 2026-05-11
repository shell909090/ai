#!/usr/bin/env python3
"""Minimal MCP server for testing MCPStdioProvider."""

from __future__ import annotations

import asyncio

from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server

server = Server("test-server")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    """Return the available test tools."""
    return [
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


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Handle tool calls."""
    if name == "echo":
        return [types.TextContent(type="text", text=arguments.get("text", ""))]
    elif name == "add":
        result = float(arguments.get("a", 0)) + float(arguments.get("b", 0))
        return [types.TextContent(type="text", text=str(result))]
    raise ValueError(f"Unknown tool: {name}")


async def main() -> None:
    """Run the MCP server over stdio."""
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
