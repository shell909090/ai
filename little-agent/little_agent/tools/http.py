"""Built-in HTTP tool provider."""

from __future__ import annotations

from collections.abc import Iterator

import aiohttp

from little_agent.types import JSONValue

from .protocol import AsyncToolFn, ToolArgDef, ToolDef


class HttpToolProvider:
    """Send HTTP requests via aiohttp."""

    _TOOL_DEF = ToolDef(
        desc="Send an HTTP request and return status, headers and body",
        args=[
            ToolArgDef("url", "string", "Request URL", True),
            ToolArgDef("method", "string", "HTTP method, default GET", False),
            ToolArgDef("headers", "object", "Request headers as key-value pairs", False),
            ToolArgDef("body", "string", "Request body", False),
            ToolArgDef("timeout", "number", "Timeout in seconds, default 30", False),
        ],
    )

    def __iter__(self) -> Iterator[tuple[str, ToolDef, AsyncToolFn]]:
        """Yield the single http tool triple."""
        yield ("http", self._TOOL_DEF, self._dispatch)

    async def _dispatch(self, args: dict[str, JSONValue]) -> JSONValue:
        """Send an HTTP request and return status, headers and body."""
        url = args.get("url")
        if not isinstance(url, str):
            raise ValueError("url must be a string")

        method_val = args.get("method")
        method = method_val if isinstance(method_val, str) else "GET"

        headers_val = args.get("headers")
        headers: dict[str, str] | None = None
        if isinstance(headers_val, dict):
            headers = {str(k): str(v) for k, v in headers_val.items()}

        body_val = args.get("body")
        body: str | None = body_val if isinstance(body_val, str) else None

        timeout_val = args.get("timeout")
        timeout: float = float(timeout_val) if isinstance(timeout_val, (int, float)) else 30.0

        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method,
                    url,
                    headers=headers,
                    data=body,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as resp:
                    resp_headers: dict[str, JSONValue] = {k: v for k, v in resp.headers.items()}
                    resp_body = await resp.text(errors="replace")
                    return {
                        "status": resp.status,
                        "headers": resp_headers,
                        "body": resp_body,
                    }
        except Exception as e:
            return {"status": -1, "headers": {}, "body": str(e)}
