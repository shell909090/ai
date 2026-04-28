"""Tests for backend request conversion."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from little_agent.agent.core import AgentCore
from little_agent.agent.nodes import (
    AssistantResponseNode,
    ToolCallNode,
    ToolResultNode,
    UserPromptNode,
)
from little_agent.backends.openai import (
    OpenAIBackend,
    _chain_to_messages,
    _tool_map_to_openai_functions,
)
from tests.mocks import MockClient, MockToolManager


def test_tool_map_to_openai_functions() -> None:
    """Test tool map conversion to OpenAI functions."""
    tool_map = {
        "echo": ("Echo", [("text", "string", "text", True)]),
    }
    functions = _tool_map_to_openai_functions(tool_map)
    assert len(functions) == 1
    assert functions[0]["function"]["name"] == "echo"
    assert "text" in functions[0]["function"]["parameters"]["properties"]


def test_chain_to_messages() -> None:
    """Test chain to messages conversion."""
    node1 = UserPromptNode(id="1", prev=None, prompt="hello")
    node2 = AssistantResponseNode(id="2", prev=node1, text="hi")
    messages = _chain_to_messages(node2)
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"


def test_chain_to_messages_with_content_block() -> None:
    """Test chain to messages with ContentBlock prompt."""
    node = UserPromptNode(id="1", prev=None, prompt=[{"type": "text", "text": "hello"}])
    messages = _chain_to_messages(node)
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == '[{"type": "text", "text": "hello"}]'


def test_chain_to_messages_with_tool_result() -> None:
    """Test chain to messages with ToolCallNode and ToolResultNode."""
    node1 = UserPromptNode(id="1", prev=None, prompt="hello")
    node2 = ToolCallNode(
        id="2", prev=node1, calls={"c1": {"tool_name": "echo", "arguments": {"text": "hi"}}}
    )
    node3 = ToolResultNode(
        id="3", prev=node2, results={"c1": {"status": "completed", "content": "hi"}}
    )
    messages = _chain_to_messages(node3)
    assert len(messages) == 3
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert messages[2]["role"] == "tool"


def test_chain_to_messages_parallel_tool_calls() -> None:
    """Test parallel tool calls merged into single assistant message."""
    node1 = UserPromptNode(id="1", prev=None, prompt="hello")
    node2 = ToolCallNode(
        id="2",
        prev=node1,
        calls={
            "c1": {"tool_name": "echo", "arguments": {"text": "a"}},
            "c2": {"tool_name": "add", "arguments": {"a": 1, "b": 2}},
        },
    )
    messages = _chain_to_messages(node2)
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert len(messages[1]["tool_calls"]) == 2


@pytest.mark.asyncio
async def test_openai_backend_generate() -> None:
    """Test OpenAI backend generate method."""
    client = MockClient()
    tools = MockToolManager(tools={"echo": ("Echo", [("text", "string", "text", True)])})
    backend = OpenAIBackend(model="gpt-4", api_key="test-key")

    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.tool_calls = None
    mock_choice.message.content = "Hello"
    mock_response.choices = [mock_choice]
    backend._client.chat.completions.create = AsyncMock(return_value=mock_response)

    agent = AgentCore(client=client, backend=backend, tools=tools)
    session = await agent.new()

    result = await backend.generate(session)
    assert result.finish_reason == "completed"
    assert result.output_text == "Hello"


@pytest.mark.asyncio
async def test_openai_backend_generate_with_tool_calls() -> None:
    """Test OpenAI backend generate with tool calls in response."""
    client = MockClient()
    tools = MockToolManager(tools={"echo": ("Echo", [("text", "string", "text", True)])})
    backend = OpenAIBackend(model="gpt-4", api_key="test-key")

    mock_tool_call = MagicMock()
    mock_tool_call.id = "c1"
    mock_tool_call.function.name = "echo"
    mock_tool_call.function.arguments = '{"text": "hello"}'

    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.tool_calls = [mock_tool_call]
    mock_choice.message.content = None
    mock_response.choices = [mock_choice]
    backend._client.chat.completions.create = AsyncMock(return_value=mock_response)

    agent = AgentCore(client=client, backend=backend, tools=tools)
    session = await agent.new()

    result = await backend.generate(session)
    assert result.finish_reason == "tool_call"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool_name == "echo"
    assert result.tool_calls[0].arguments == {"text": "hello"}
