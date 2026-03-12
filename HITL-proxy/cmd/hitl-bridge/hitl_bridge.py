#!/usr/bin/env python3
"""hitl-bridge: stdio ↔ SSE bridge for MCP with Bearer token auth."""

import argparse
import asyncio
import json
import logging
import sys
from typing import Any

from anyio.streams.memory import MemoryObjectSendStream
from mcp.client.session import ClientSession
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
    parser.add_argument(
        "--ping",
        action="store_true",
        help="Test connectivity: connect, initialize, ping, then exit",
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


def _build_headers(api_key: str) -> dict[str, str] | None:
    """Build HTTP headers dict from API key."""
    if api_key:
        return {"Authorization": f"Bearer {api_key}"}
    return None


async def ping(url: str, api_key: str) -> None:
    """Connect, initialize MCP session, send ping, then exit."""
    async with sse_client(url, headers=_build_headers(api_key)) as (
        read_stream,
        write_stream,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            await session.send_ping()
            print("ok")


async def run(url: str, api_key: str) -> None:
    """Run the stdio ↔ SSE bridge."""
    async with sse_client(url, headers=_build_headers(api_key)) as (
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
        if args.ping:
            asyncio.run(ping(args.url, args.api_key))
        else:
            asyncio.run(run(args.url, args.api_key))
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        logger.error("%s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
