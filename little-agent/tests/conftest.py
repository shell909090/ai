"""Pytest fixtures."""

import pytest

from little_agent.agent.core import AgentCore
from tests.mocks import MockBackend, MockClient, MockToolManager


@pytest.fixture
def mock_client() -> MockClient:
    """Return a mock client."""
    return MockClient()


@pytest.fixture
def mock_backend() -> MockBackend:
    """Return a mock backend."""
    return MockBackend()


@pytest.fixture
def mock_tools() -> MockToolManager:
    """Return a mock tool manager."""
    return MockToolManager(
        tools={
            "echo": ("Echo tool", [("text", "string", "text", True)]),
            "add": ("Add tool", [("a", "number", "a", True), ("b", "number", "b", True)]),
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
    mock_tools: MockToolManager,
) -> AgentCore:
    """Return an agent with mock dependencies."""
    return AgentCore(client=mock_client, backend=mock_backend, tools=mock_tools)
