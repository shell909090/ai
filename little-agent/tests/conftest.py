"""Pytest fixtures."""

import pytest

from little_agent.agent.agent import AgentCore
from little_agent.tools.protocol import ToolArgDef, ToolDef
from tests.mocks import MockBackend, MockClient, MockToolProvider


@pytest.fixture
def mock_client() -> MockClient:
    """Return a mock client."""
    return MockClient()


@pytest.fixture
def mock_backend() -> MockBackend:
    """Return a mock backend."""
    return MockBackend()


@pytest.fixture
def mock_tools() -> MockToolProvider:
    """Return a mock tool provider."""
    return MockToolProvider(
        tools={
            "echo": ToolDef(
                desc="Echo tool",
                args=[ToolArgDef(name="text", type="string", desc="text", required=True)],
            ),
            "add": ToolDef(
                desc="Add tool",
                args=[
                    ToolArgDef(name="a", type="number", desc="a", required=True),
                    ToolArgDef(name="b", type="number", desc="b", required=True),
                ],
            ),
        },
        responses={
            "echo": "echoed",
            "add": 42,
        },
    )


@pytest.fixture
def agent(
    mock_client: MockClient,
    mock_backend: MockBackend,
    mock_tools: MockToolProvider,
) -> AgentCore:
    """Return an agent with mock dependencies."""
    return AgentCore(client=mock_client, backend=mock_backend, tools=mock_tools)
