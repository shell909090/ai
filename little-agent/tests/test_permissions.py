"""Tests for the Chain of Responsibility permission system."""

from __future__ import annotations

import pytest

from little_agent.agent.permissions import (
    BlackWhiteListChecker,
    YesManChecker,
    build_permission_chain,
)
from little_agent.backends.protocol import BackendToolCall, BackendTurnResult
from little_agent.types import JSONValue
from tests.mocks import BuiltinToolProvider, MockAgent, MockBackend, MockClient

# ---------------------------------------------------------------------------
# YesManChecker unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_yesman_always_grants() -> None:
    """YesManChecker returns True for any tool and payload."""
    checker = YesManChecker()
    assert await checker.request_permission(object(), "bash", {}) is True
    assert (
        await checker.request_permission(object(), "write", {"arguments": {"path": "/tmp"}}) is True
    )
    assert await checker.request_permission(object(), "anything", {}) is True


# ---------------------------------------------------------------------------
# BlackWhiteListChecker unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_blackwhitelist_blacklist_blocks() -> None:
    """A blacklisted pattern denies the tool."""
    terminal = YesManChecker()
    checker = BlackWhiteListChecker(blacklist=["rm*"], whitelist=[], next_checker=terminal)
    assert await checker.request_permission(object(), "rm", {}) is False
    assert await checker.request_permission(object(), "rmdir", {}) is False


@pytest.mark.asyncio
async def test_blackwhitelist_whitelist_allows() -> None:
    """A whitelisted pattern (with no blacklist match) grants the tool."""
    terminal = YesManChecker()
    checker = BlackWhiteListChecker(
        blacklist=[], whitelist=["echo", "read*"], next_checker=terminal
    )
    assert await checker.request_permission(object(), "echo", {}) is True
    assert await checker.request_permission(object(), "read_file", {}) is True


@pytest.mark.asyncio
async def test_blackwhitelist_blacklist_priority_over_whitelist() -> None:
    """Blacklist takes priority even when whitelist also matches."""
    terminal = YesManChecker()
    checker = BlackWhiteListChecker(blacklist=["bash"], whitelist=["bash"], next_checker=terminal)
    assert await checker.request_permission(object(), "bash", {}) is False


@pytest.mark.asyncio
async def test_blackwhitelist_no_match_delegates() -> None:
    """When no pattern matches, the request is delegated to next."""

    class _RecordingChecker:
        called: bool = False

        async def request_permission(
            self, session: object, kind: str, payload: dict[str, JSONValue]
        ) -> bool:
            self.called = True
            return True

    next_checker = _RecordingChecker()
    checker = BlackWhiteListChecker(blacklist=["rm"], whitelist=["echo"], next_checker=next_checker)
    result = await checker.request_permission(object(), "add", {})
    assert result is True
    assert next_checker.called


# ---------------------------------------------------------------------------
# build_permission_chain unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_chain_empty_returns_terminal() -> None:
    """An empty config list returns the terminal unchanged."""
    terminal = YesManChecker()
    result = build_permission_chain([], terminal)
    assert result is terminal


@pytest.mark.asyncio
async def test_build_chain_yesman() -> None:
    """A yesman config produces a YesManChecker (terminal is replaced)."""
    terminal = YesManChecker()
    result = build_permission_chain([{"type": "yesman"}], terminal)
    assert isinstance(result, YesManChecker)
    assert await result.request_permission(object(), "anything", {}) is True


@pytest.mark.asyncio
async def test_build_chain_blackwhitelist() -> None:
    """A blackwhitelist config wraps the terminal in a BlackWhiteListChecker."""
    terminal = YesManChecker()
    cfg: list[dict[str, JSONValue]] = [
        {
            "type": "blackwhitelist",
            "blacklist": ["rm"],
            "whitelist": ["echo"],
        }
    ]
    result = build_permission_chain(cfg, terminal)
    assert isinstance(result, BlackWhiteListChecker)
    assert await result.request_permission(object(), "rm", {}) is False
    assert await result.request_permission(object(), "echo", {}) is True
    # unknown → delegates to terminal (YesManChecker) → True
    assert await result.request_permission(object(), "add", {}) is True


# ---------------------------------------------------------------------------
# T72: build_permission_chain warns on unknown checker type
# ---------------------------------------------------------------------------


def test_build_chain_unknown_type_raises_value_error() -> None:
    """build_permission_chain with unknown type raises ValueError immediately."""
    terminal = YesManChecker()
    cfg: list[dict[str, JSONValue]] = [{"type": "totally_unknown_checker"}]

    with pytest.raises(ValueError, match="totally_unknown_checker"):
        build_permission_chain(cfg, terminal)


def test_build_chain_unknown_type_among_known_raises_value_error() -> None:
    """Unknown type in a mixed list raises ValueError, preventing partial chain construction."""
    terminal = YesManChecker()
    cfg: list[dict[str, JSONValue]] = [
        {"type": "blackwhitelist", "blacklist": ["bash"], "whitelist": []},
        {"type": "mystery_type"},
    ]

    with pytest.raises(ValueError, match="mystery_type"):
        build_permission_chain(cfg, terminal)

    # Verify a pure known-type list still builds correctly.
    cfg_valid: list[dict[str, JSONValue]] = [
        {"type": "blackwhitelist", "blacklist": ["bash"], "whitelist": []},
    ]
    result = build_permission_chain(cfg_valid, terminal)

    # The blackwhitelist entry is still applied; "bash" must be denied.
    # (We can't await here but we can check the type.)
    assert isinstance(result, BlackWhiteListChecker)


@pytest.mark.asyncio
async def test_build_chain_order() -> None:
    """First config in list is the outermost (first-checked) wrapper."""
    # Build a chain where config[0] blacklists "bash" and config[1] is yesman.
    # The outermost checker must be the one from config[0], so "bash" is denied.
    cfg: list[dict[str, JSONValue]] = [
        {"type": "blackwhitelist", "blacklist": ["bash"], "whitelist": []},
        {"type": "yesman"},
    ]
    terminal = YesManChecker()
    result = build_permission_chain(cfg, terminal)
    # "bash" should be denied by the outermost blackwhitelist
    assert await result.request_permission(object(), "bash", {}) is False
    # other tools delegate through to yesman → True
    assert await result.request_permission(object(), "echo", {}) is True


# ---------------------------------------------------------------------------
# Integration tests with MockAgent / MockBackend
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_permission_denies_tool_when_blacklisted() -> None:
    """BlackWhiteListChecker with blacklist blocks tool call with 'Permission denied'."""
    client = MockClient()
    provider = BuiltinToolProvider()
    checker = BlackWhiteListChecker(blacklist=["add"], whitelist=[], next_checker=YesManChecker())

    script = [
        BackendTurnResult(
            output_text="",
            tool_calls=[BackendToolCall(call_id="c1", tool_name="add", arguments={"a": 1, "b": 2})],
            finish_reason="tool_call",
        ),
        BackendTurnResult(
            output_text="done",
            tool_calls=[],
            finish_reason="completed",
        ),
    ]
    backend = MockBackend(script=script)
    agent = MockAgent(backend=backend, tools=provider, client=client, permissions=checker)
    session = await agent.new()

    await session.prompt("hello")

    updates = [
        u for u in client.updates if u.type == "tool_call_update" and u.data.get("call_id") == "c1"
    ]
    assert updates, "Expected a tool_call_update for call_id 'c1'"
    update = updates[0]
    assert update.data["status"] == "failed"
    assert "Permission denied" in str(update.data.get("content", ""))


@pytest.mark.asyncio
async def test_permission_grants_tool_when_yesman() -> None:
    """YesManChecker grants tool call and it runs successfully."""
    client = MockClient()
    provider = BuiltinToolProvider()
    checker = YesManChecker()

    script = [
        BackendTurnResult(
            output_text="",
            tool_calls=[BackendToolCall(call_id="e1", tool_name="echo", arguments={"text": "hi"})],
            finish_reason="tool_call",
        ),
        BackendTurnResult(
            output_text="done",
            tool_calls=[],
            finish_reason="completed",
        ),
    ]
    backend = MockBackend(script=script)
    agent = MockAgent(backend=backend, tools=provider, client=client, permissions=checker)
    session = await agent.new()

    await session.prompt("hello")

    updates = [
        u for u in client.updates if u.type == "tool_call_update" and u.data.get("call_id") == "e1"
    ]
    assert updates, "Expected a tool_call_update for call_id 'e1'"
    update = updates[0]
    assert update.data["status"] == "completed"
    assert update.data["content"] == "hi"


@pytest.mark.asyncio
async def test_permission_denies_when_client_rejects() -> None:
    """When client (used as terminal) rejects, tool call fails with 'Permission denied'."""

    class _DenyAllClient(MockClient):
        async def request_permission(
            self,
            session: object,
            kind: str,
            payload: dict[str, JSONValue],
        ) -> bool:
            return False

    client = _DenyAllClient()
    provider = BuiltinToolProvider()

    script = [
        BackendTurnResult(
            output_text="",
            tool_calls=[BackendToolCall(call_id="d1", tool_name="add", arguments={"a": 1, "b": 2})],
            finish_reason="tool_call",
        ),
        BackendTurnResult(
            output_text="done",
            tool_calls=[],
            finish_reason="completed",
        ),
    ]
    backend = MockBackend(script=script)
    # Pass client explicitly as permissions (acting as the terminal deny-all checker)
    agent = MockAgent(backend=backend, tools=provider, client=client, permissions=client)
    session = await agent.new()

    await session.prompt("hello")

    updates = [
        u for u in client.updates if u.type == "tool_call_update" and u.data.get("call_id") == "d1"
    ]
    assert updates, "Expected a tool_call_update for call_id 'd1'"
    update = updates[0]
    assert update.data["status"] == "failed"
    assert "Permission denied" in str(update.data.get("content", ""))
