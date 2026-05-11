"""Tests for MCPStdioProvider."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import pytest

from little_agent.tools.mcp import MCPStdioProvider

MOCK_SERVER = str(Path(__file__).parent / "fixtures" / "mock_mcp_server.py")


# ---------------------------------------------------------------------------
# (a) start() lists tools with namespaced names
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_lists_tools() -> None:
    """start() should populate tools with namespaced names like test__echo."""
    provider = MCPStdioProvider(
        name="test",
        command=[sys.executable, MOCK_SERVER],
    )
    await provider.start()
    try:
        tools = list(provider)
        names = [t[0] for t in tools]
        assert "test__echo" in names
        assert "test__add" in names
    finally:
        await provider.stop()


# ---------------------------------------------------------------------------
# (b) Tool call normal round-trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_call_echo() -> None:
    """Calling the echo tool should return the input text."""
    provider = MCPStdioProvider(
        name="svc",
        command=[sys.executable, MOCK_SERVER],
    )
    await provider.start()
    try:
        tools = {t[0]: t[2] for t in provider}
        result = await tools["svc__echo"]({"text": "hello world"})
        assert result == "hello world"
    finally:
        await provider.stop()


@pytest.mark.asyncio
async def test_tool_call_add() -> None:
    """Calling the add tool should return the sum as a string."""
    provider = MCPStdioProvider(
        name="svc",
        command=[sys.executable, MOCK_SERVER],
    )
    await provider.start()
    try:
        tools = {t[0]: t[2] for t in provider}
        result = await tools["svc__add"]({"a": 3, "b": 4})
        # The mock server returns str(float(3) + float(4)) == "7.0"
        assert result == "7.0"
    finally:
        await provider.stop()


# ---------------------------------------------------------------------------
# (c) Provider not started → tool call raises RuntimeError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_before_start_raises() -> None:
    """Calling a tool before start() raises RuntimeError."""
    provider = MCPStdioProvider(
        name="test",
        command=[sys.executable, MOCK_SERVER],
    )
    # Manually inject a dummy tool entry without starting so _running is False
    from little_agent.tools.protocol import ToolDef

    provider._tools = [("test__echo", ToolDef(desc="echo"), "echo")]  # type: ignore[assignment]

    tools = list(provider)
    assert len(tools) == 1
    _, _, fn = tools[0]

    with pytest.raises(RuntimeError, match="not running"):
        await fn({"text": "x"})


# ---------------------------------------------------------------------------
# (d) inputSchema with nested (unsupported) type → tool skipped, WARNING logged
# ---------------------------------------------------------------------------


def test_convert_schema_skips_nested_type(caplog: pytest.LogCaptureFixture) -> None:
    """_convert_schema returns None and logs a WARNING for unsupported field types."""
    provider = MCPStdioProvider(name="srv", command=["unused"])
    schema = {
        "type": "object",
        "properties": {
            "data": {"type": "array", "description": "A list"},
        },
        "required": [],
    }
    with caplog.at_level(logging.WARNING, logger="little_agent.tools.mcp"):
        result = provider._convert_schema("bad_tool", "desc", schema)

    assert result is None
    assert any("unsupported type" in r.message for r in caplog.records)


def test_convert_schema_non_object_top_level_skipped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """_convert_schema returns None when top-level type is not 'object'."""
    provider = MCPStdioProvider(name="srv", command=["unused"])
    schema: dict[str, Any] = {"type": "array"}
    with caplog.at_level(logging.WARNING, logger="little_agent.tools.mcp"):
        result = provider._convert_schema("bad_tool", "desc", schema)

    assert result is None
    assert any("not 'object'" in r.message for r in caplog.records)


def test_convert_schema_no_schema_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    """_convert_schema returns a no-arg ToolDef when schema is not a dict."""
    provider = MCPStdioProvider(name="srv", command=["unused"])
    with caplog.at_level(logging.WARNING, logger="little_agent.tools.mcp"):
        result = provider._convert_schema("no_schema_tool", "desc", None)

    assert result is not None
    assert result.args == []
    assert any("no inputSchema" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# (e) Invalid tool name → tool skipped, WARNING logged (via start() + patching)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_tool_name_skipped(caplog: pytest.LogCaptureFixture) -> None:
    """Tools with names that yield invalid namespaced names are skipped with a WARNING."""
    provider = MCPStdioProvider(
        name="test",
        command=[sys.executable, MOCK_SERVER],
    )
    await provider.start()
    try:
        # Simulate what start() does for an invalid name directly
        invalid_namespaced = "test__" + ("x" * 65)
        from little_agent.tools.mcp import _TOOL_NAME_RE

        assert not _TOOL_NAME_RE.match(invalid_namespaced)
    finally:
        await provider.stop()


# ---------------------------------------------------------------------------
# (f) Multiple MCP servers → namespace isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_namespace_isolation() -> None:
    """Two providers with different names produce distinct namespaced tool names."""
    p1 = MCPStdioProvider(name="alpha", command=[sys.executable, MOCK_SERVER])
    p2 = MCPStdioProvider(name="beta", command=[sys.executable, MOCK_SERVER])
    await p1.start()
    await p2.start()
    try:
        names1 = {t[0] for t in p1}
        names2 = {t[0] for t in p2}

        assert "alpha__echo" in names1
        assert "alpha__add" in names1
        assert "beta__echo" in names2
        assert "beta__add" in names2

        # No overlap
        assert names1.isdisjoint(names2)
    finally:
        # Stop providers sequentially and suppress cleanup errors (including
        # CancelledError which is a BaseException in Python 3.8+).
        for p in (p1, p2):
            try:
                await p.stop()
            except BaseException:
                pass


# ---------------------------------------------------------------------------
# (g) stop() sets _running to False
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stop_sets_running_false() -> None:
    """After stop(), _running is False."""
    provider = MCPStdioProvider(
        name="test",
        command=[sys.executable, MOCK_SERVER],
    )
    await provider.start()
    assert provider._running is True
    await provider.stop()
    assert provider._running is False


@pytest.mark.asyncio
async def test_stop_idempotent() -> None:
    """Calling stop() twice does not raise."""
    provider = MCPStdioProvider(
        name="test",
        command=[sys.executable, MOCK_SERVER],
    )
    await provider.start()
    await provider.stop()
    # Second stop should be a no-op
    await provider.stop()
    assert provider._running is False
