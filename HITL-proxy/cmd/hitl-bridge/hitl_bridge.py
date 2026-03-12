#!/usr/bin/env python3
"""hitl-bridge: stdio ↔ SSE bridge for MCP with Bearer token auth."""

import argparse
import asyncio
import json
import logging
import sys
from typing import Any

from anyio.streams.memory import MemoryObjectSendStream
from mcp.client.sse import sse_client
from mcp.shared.message import SessionMessage
from mcp.types import JSONRPCMessage, JSONRPCNotification, JSONRPCRequest

logger = logging.getLogger("hitl-bridge")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="stdio ↔ SSE bridge for MCP")
    parser.add_argument(
        "--url",
        default="http://localhost:8080/mcp/sse",
        help="SSE endpoint URL (default: %(default)s)",
    )
    parser.add_argument(
        "--api-key",
        default="",
        help="Bearer token for authentication",
    )
    return parser.parse_args()


def build_message(data: dict[str, Any]) -> JSONRPCMessage:
    """Build a JSONRPCMessage from a parsed JSON dict."""
    if "id" in data:
        return JSONRPCMessage(
            JSONRPCRequest(
                jsonrpc="2.0",
                id=data["id"],
                method=data["method"],
                params=data.get("params"),
            )
        )
    return JSONRPCMessage(
        JSONRPCNotification(
            jsonrpc="2.0",
            method=data["method"],
            params=data.get("params"),
        )
    )


async def read_stdin(
    write_stream: MemoryObjectSendStream[SessionMessage],
) -> None:
    """Read JSON-RPC messages from stdin and forward to SSE."""
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin.buffer)

    while True:
        line = await reader.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            msg = build_message(data)
            await write_stream.send(SessionMessage(msg))
        except Exception:
            logger.exception("process stdin message")


async def read_sse(
    read_stream: Any,
) -> None:
    """Read messages from SSE and write to stdout."""
    async for item in read_stream:
        if isinstance(item, Exception):
            logger.error("SSE error: %s", item)
            continue
        try:
            output = item.message.model_dump_json(by_alias=True, exclude_none=True)
            sys.stdout.write(output + "\n")
            sys.stdout.flush()
        except Exception:
            logger.exception("write to stdout")


async def run(url: str, api_key: str) -> None:
    """Run the stdio ↔ SSE bridge."""
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    async with sse_client(url, headers=headers or None) as (
        read_stream,
        write_stream,
    ):
        async with asyncio.TaskGroup() as tg:
            tg.create_task(read_stdin(write_stream))
            tg.create_task(read_sse(read_stream))


def main() -> None:
    """Entry point for the hitl-bridge CLI."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    args = parse_args()
    try:
        asyncio.run(run(args.url, args.api_key))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
