"""Tests for permission system."""

from __future__ import annotations

import pytest

from little_agent.agent.permissions import PermissionManager, PermissionRule
from little_agent.backends.protocol import BackendToolCall, BackendTurnResult
from little_agent.tools.protocol import ToolDef, ToolProvider
from little_agent.types import JSONValue
from tests.mocks import BuiltinToolProvider, MockAgent, MockBackend, MockClient


class _DenyAllClient(MockClient):
    """Mock client that denies all permission requests."""

    async def request_permission(
        self,
        session: object,
        kind: str,
        payload: dict[str, JSONValue],
    ) -> bool:
        return False


class _AskToolProvider(ToolProvider):
    """Provider with tools for permission testing."""

    def __iter__(self):  # type: ignore[override]
        _empty_def = ToolDef(desc="", args=[])
        for name in ("bash", "read", "write"):

            async def _fn(args: dict[str, JSONValue], _n: str = name) -> JSONValue:
                return f"{_n}-result"

            yield name, _empty_def, _fn


@pytest.mark.asyncio
async def test_permission_manager_default_allow() -> None:
    """Default allow grants all tools."""
    pm = PermissionManager(default="allow")
    assert pm.check("bash") == "allow"
    assert pm.check("anything") == "allow"


@pytest.mark.asyncio
async def test_permission_manager_default_deny() -> None:
    """Default deny blocks all tools."""
    pm = PermissionManager(default="deny")
    assert pm.check("bash") == "deny"
    assert pm.check("read") == "deny"


@pytest.mark.asyncio
async def test_permission_manager_rule_override() -> None:
    """Specific rules override default."""
    pm = PermissionManager(
        rules=[
            PermissionRule(tool="bash", action="ask"),
            PermissionRule(tool="write", action="deny"),
        ],
        default="allow",
    )
    assert pm.check("bash") == "ask"
    assert pm.check("write") == "deny"
    assert pm.check("read") == "allow"


@pytest.mark.asyncio
async def test_permission_manager_from_config() -> None:
    """Build PermissionManager from config dict."""
    config = {
        "default": "deny",
        "rules": [
            {"tool": "bash", "action": "ask"},
            {"tool": "read", "action": "allow"},
        ],
    }
    pm = PermissionManager.from_config(config)
    assert pm.check("bash") == "ask"
    assert pm.check("read") == "allow"
    assert pm.check("write") == "deny"


@pytest.mark.asyncio
async def test_permission_manager_from_none_config() -> None:
    """None config produces default-ask manager."""
    pm = PermissionManager.from_config(None)
    assert pm.check("anything") == "ask"


@pytest.mark.asyncio
async def test_permission_deny_blocks_tool() -> None:
    """When permission is deny, tool call is recorded as failed without invocation."""
    client = MockClient()
    provider = BuiltinToolProvider()
    pm = PermissionManager(
        rules=[PermissionRule(tool="add", action="deny")],
        default="allow",
    )

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
    agent = MockAgent(backend=backend, tools=provider, client=client, permissions=pm)
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
async def test_permission_ask_grants_when_allowed() -> None:
    """When permission is ask and client grants, tool is invoked."""
    client = MockClient()
    provider = BuiltinToolProvider()
    pm = PermissionManager(
        rules=[PermissionRule(tool="echo", action="ask")],
        default="allow",
    )

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
    agent = MockAgent(backend=backend, tools=provider, client=client, permissions=pm)
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
async def test_permission_ask_denies_when_rejected() -> None:
    """When permission is ask and client rejects, tool is not invoked."""
    client = _DenyAllClient()
    provider = BuiltinToolProvider()
    pm = PermissionManager(
        rules=[PermissionRule(tool="echo", action="ask")],
        default="allow",
    )

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
    agent = MockAgent(backend=backend, tools=provider, client=client, permissions=pm)
    session = await agent.new()

    await session.prompt("hello")

    updates = [
        u for u in client.updates if u.type == "tool_call_update" and u.data.get("call_id") == "e1"
    ]
    assert updates, "Expected a tool_call_update for call_id 'e1'"
    update = updates[0]
    assert update.data["status"] == "failed"
    assert "Permission denied" in str(update.data.get("content", ""))
