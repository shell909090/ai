"""Tests for shared backend utilities: chain→messages, tool result formatting."""

from __future__ import annotations

from little_agent.agent.nodes import (
    AssistantNode,
    Node,
    ToolResultNode,
    UserPromptNode,
)
from little_agent.backends.openai import (
    _chain_to_messages,
    _tool_map_to_openai_functions,
)
from little_agent.tools.protocol import ToolArgDef, ToolDef


class _FakeSession:
    """Minimal session-like object for backend tests."""

    def __init__(
        self,
        messages: list[Node],
        system_prompt: str | None = None,
        summaries: list[str] | None = None,
    ) -> None:
        self.messages = messages
        self.system_prompt = system_prompt
        self.summaries = summaries or []


def test_tool_map_to_openai_functions() -> None:
    """Test tool map conversion to OpenAI functions."""
    tool_map = {
        "echo": ToolDef(desc="Echo", args=[ToolArgDef("text", "string", "text", True)]),
    }
    functions = _tool_map_to_openai_functions(tool_map)
    assert len(functions) == 1
    assert functions[0]["function"]["name"] == "echo"
    assert "text" in functions[0]["function"]["parameters"]["properties"]


def test_chain_to_messages() -> None:
    """Test chain to messages conversion."""
    node1 = UserPromptNode(id="1", prompt="hello")
    node2 = AssistantNode(id="2", text="hi")
    session = _FakeSession([node1, node2])
    messages = _chain_to_messages(session)
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"


def test_chain_to_messages_with_content_block() -> None:
    """Test chain to messages with ContentBlock prompt."""
    node = UserPromptNode(id="1", prompt=[{"type": "text", "text": "hello"}])
    session = _FakeSession([node])
    messages = _chain_to_messages(session)
    assert len(messages) == 1
    assert messages[0]["role"] == "user"


def test_chain_to_messages_with_tool_result() -> None:
    """Test chain to messages with AssistantNode (tool_calls) and ToolResultNode."""
    node1 = UserPromptNode(id="1", prompt="hello")
    node2 = AssistantNode(
        id="2", tool_calls={"c1": {"tool_name": "echo", "arguments": {"text": "hi"}}}
    )
    node3 = ToolResultNode(id="3", results={"c1": {"status": "completed", "content": "hi"}})
    session = _FakeSession([node1, node2, node3])
    messages = _chain_to_messages(session)
    assert len(messages) == 3
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert messages[2]["role"] == "tool"
    assert messages[2]["content"] == "status: completed\ncontent: hi"


def test_format_tool_result_plain_string() -> None:
    """String values are written as-is without JSON escaping."""
    node = ToolResultNode(
        id="t1",
        results={"c1": {"status": "completed", "content": "line1\nline2\npath: /foo/bar"}},
    )
    msgs = node.to_anthropic()
    expected = "status: completed\ncontent: line1\nline2\npath: /foo/bar"
    assert msgs[0]["content"][0]["content"] == expected


def test_format_tool_result_non_string_value() -> None:
    """Non-string values fall back to json.dumps."""
    node = ToolResultNode(
        id="t1",
        results={"c1": {"status": "completed", "content": {"key": "val"}}},
    )
    msgs = node.to_anthropic()
    assert msgs[0]["content"][0]["content"] == 'status: completed\ncontent: {"key": "val"}'


def test_chain_to_messages_parallel_tool_calls() -> None:
    """Test parallel tool calls merged into single assistant message."""
    node1 = UserPromptNode(id="1", prompt="hello")
    node2 = AssistantNode(
        id="2",
        tool_calls={
            "c1": {"tool_name": "echo", "arguments": {"text": "a"}},
            "c2": {"tool_name": "add", "arguments": {"a": 1, "b": 2}},
        },
    )
    session = _FakeSession([node1, node2])
    messages = _chain_to_messages(session)
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert len(messages[1]["tool_calls"]) == 2


def test_assistant_node_text_in_messages_openai() -> None:
    """to_openai includes content when text is non-empty."""
    n = AssistantNode(
        id="n1",
        text="I will use bash",
        tool_calls={"c1": {"tool_name": "bash", "arguments": {"cmd": "ls"}}},
    )
    msgs = n.to_openai()
    assert len(msgs) == 1
    msg = msgs[0]
    assert msg["role"] == "assistant"
    assert msg.get("content") == "I will use bash"
    assert "tool_calls" in msg
    assert len(msg["tool_calls"]) == 1
    assert msg["tool_calls"][0]["function"]["name"] == "bash"


def test_assistant_node_empty_text_in_messages_openai() -> None:
    """to_openai omits content key when text is empty."""
    n = AssistantNode(
        id="n2",
        text="",
        tool_calls={"c1": {"tool_name": "echo", "arguments": {"text": "hi"}}},
    )
    msgs = n.to_openai()
    assert len(msgs) == 1
    msg = msgs[0]
    assert msg["role"] == "assistant"
    assert "content" not in msg
    assert "tool_calls" in msg
