"""Shared helpers for CI integration tests."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from little_agent.agent.agent import AgentCore
from little_agent.agent.permissions import YesManChecker
from little_agent.backends.build import _DEFAULT_BACKEND_CONFIG, _build_backend
from little_agent.main import _deep_merge
from little_agent.tools.bash import BashToolProvider
from little_agent.tools.manager import ToolManager
from tests.mocks import MockClient


def make_backend(config: dict[str, Any]) -> Any:
    """Build primary backend from merged config."""
    backends_cfg = config.get("backends", {})
    primary_cfg = backends_cfg.get("primary", {})
    if not isinstance(primary_cfg, dict):
        pytest.skip("backends.primary missing in CI config")
    return _build_backend(_deep_merge(_DEFAULT_BACKEND_CONFIG, primary_cfg), "primary")


def build_agent(config: dict[str, Any]) -> tuple[AgentCore, MockClient]:
    """Build an AgentCore from config with real backend and bash tool."""
    backend = make_backend(config)
    tools = ToolManager()
    tools.register(BashToolProvider())
    client: MockClient = MockClient()
    agent = AgentCore(
        client=client,
        backend=backend,
        tools=tools,
        permissions=YesManChecker(),
    )
    return agent, client


def walk_chain(session: Any) -> list[Any]:
    """Return all nodes in the chain from tail back to head."""
    nodes = []
    node = session.tail
    while node is not None:
        nodes.append(node)
        node = node.prev
    return nodes


def make_ws_mock() -> MagicMock:
    """Create a minimal WebSocket mock with async send methods."""
    ws = MagicMock()
    ws.send_str = AsyncMock()
    ws.send_json = AsyncMock()
    return ws
