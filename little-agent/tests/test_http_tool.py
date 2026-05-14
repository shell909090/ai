"""Tests for HTTP tool provider."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from little_agent.agent.tool_manager import ToolManager
from little_agent.tools.http import HttpProvider


def _make_manager() -> ToolManager:
    mgr = ToolManager()
    mgr.register(HttpProvider())
    return mgr


def _make_mock_session(
    status: int = 200,
    headers: dict[str, str] | None = None,
    body: str = "",
) -> tuple[MagicMock, MagicMock]:
    """Return (mock_session, mock_response) configured for aiohttp context-manager use."""
    mock_resp = AsyncMock()
    mock_resp.status = status
    mock_resp.headers = headers if headers is not None else {}
    mock_resp.text = AsyncMock(return_value=body)

    mock_resp_cm = AsyncMock()
    mock_resp_cm.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp_cm.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.request = MagicMock(return_value=mock_resp_cm)

    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_cm.__aexit__ = AsyncMock(return_value=False)

    return mock_session, mock_session_cm


@pytest.fixture
def mock_session() -> MagicMock:
    """Minimal session mock for tool dispatch (session param is unused by http tool)."""
    s = MagicMock()
    s.id = "mock-session"
    return s


def test_http_tool_listed() -> None:
    """HttpProvider.__iter__ yields 'http' with url as required parameter."""
    provider = HttpProvider()
    tools = {name: tooldef for name, tooldef, _ in provider}
    assert "http" in tools
    arg_map = {arg.name: arg for arg in tools["http"].args}
    assert "url" in arg_map
    assert arg_map["url"].required is True


@pytest.mark.asyncio
async def test_http_get(mock_session: MagicMock) -> None:
    """HTTP GET returns status, headers, and body from response."""
    mock_session, mock_session_cm = _make_mock_session(
        status=200,
        headers={"Content-Type": "text/plain"},
        body="hello",
    )
    with patch("aiohttp.ClientSession", return_value=mock_session_cm):
        mgr = _make_manager()
        result = await mgr["http"]({"url": "http://example.com"}, mock_session)

    assert isinstance(result, dict)
    assert result["status"] == 200
    assert result["body"] == "hello"
    assert isinstance(result["headers"], dict)


@pytest.mark.asyncio
async def test_http_post_with_body(mock_session: MagicMock) -> None:
    """HTTP POST with body passes method and data to session.request."""
    mock_session, mock_session_cm = _make_mock_session(status=201, body="created")
    with patch("aiohttp.ClientSession", return_value=mock_session_cm):
        mgr = _make_manager()
        result = await mgr["http"](
            {"url": "http://example.com/api", "method": "POST", "body": "data"}, mock_session
        )

    assert isinstance(result, dict)
    assert result["status"] == 201
    call_kwargs = mock_session.request.call_args
    assert call_kwargs is not None
    # method and url must be present in args or kwargs
    args, kwargs = call_kwargs
    called_method = args[0] if args else kwargs.get("method", "")
    called_url = args[1] if len(args) > 1 else kwargs.get("url", "")
    assert called_method.upper() == "POST"
    assert "example.com" in called_url
    # body passed as data keyword
    assert kwargs.get("data") == "data"


@pytest.mark.asyncio
async def test_http_custom_headers(mock_session: MagicMock) -> None:
    """Custom headers are forwarded to session.request."""
    mock_session, mock_session_cm = _make_mock_session(status=200, body="ok")
    with patch("aiohttp.ClientSession", return_value=mock_session_cm):
        mgr = _make_manager()
        await mgr["http"]({"url": "http://example.com", "headers": {"X-Foo": "bar"}}, mock_session)

    call_kwargs = mock_session.request.call_args
    assert call_kwargs is not None
    _, kwargs = call_kwargs
    passed_headers = kwargs.get("headers", {})
    assert passed_headers.get("X-Foo") == "bar"


@pytest.mark.asyncio
async def test_http_network_error(mock_session: MagicMock) -> None:
    """aiohttp.ClientError results in status=-1 response."""
    import aiohttp

    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(side_effect=aiohttp.ClientError("connection refused"))
    mock_session_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=mock_session_cm):
        mgr = _make_manager()
        result = await mgr["http"]({"url": "http://unreachable.example.com"}, mock_session)

    assert isinstance(result, dict)
    assert result["status"] == -1
    assert result["headers"] == {}
    assert isinstance(result["body"], str)


@pytest.mark.asyncio
async def test_http_invalid_url_type(mock_session: MagicMock) -> None:
    """Passing a non-string url raises ValueError."""
    mgr = _make_manager()
    with pytest.raises(ValueError):
        await mgr["http"]({"url": 123}, mock_session)
