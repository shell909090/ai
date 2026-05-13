"""Tests for Node.to_anthropic() and Node.to_openai() serialization methods."""

from __future__ import annotations

import json

from little_agent.agent.nodes import (
    AssistantNode,
    ToolResultNode,
    UserPromptNode,
)

# ---------------------------------------------------------------------------
# UserPromptNode
# ---------------------------------------------------------------------------


def test_user_prompt_str_to_anthropic() -> None:
    """String prompt produces a user message with string content."""
    n = UserPromptNode(id="1", prompt="hello")
    msgs = n.to_anthropic()
    assert msgs == [{"role": "user", "content": "hello"}]


def test_user_prompt_str_to_openai() -> None:
    """String prompt produces a user message with string content."""
    n = UserPromptNode(id="1", prompt="hello")
    msgs = n.to_openai()
    assert msgs == [{"role": "user", "content": "hello"}]


def test_user_prompt_content_block_to_anthropic() -> None:
    """List prompt is passed through directly as content list."""
    prompt = [{"type": "text", "text": "hi"}]
    n = UserPromptNode(id="1", prompt=prompt)
    msgs = n.to_anthropic()
    assert len(msgs) == 1
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == prompt


def test_user_prompt_content_block_to_openai() -> None:
    """List prompt is passed through directly as content list."""
    prompt = [{"type": "text", "text": "hi"}]
    n = UserPromptNode(id="1", prompt=prompt)
    msgs = n.to_openai()
    assert len(msgs) == 1
    assert msgs[0]["content"] == prompt


# ---------------------------------------------------------------------------
# AssistantNode (no tool_calls)
# ---------------------------------------------------------------------------


def test_assistant_text_to_anthropic() -> None:
    """Produces assistant message with text content block."""
    n = AssistantNode(id="2", text="reply")
    msgs = n.to_anthropic()
    assert len(msgs) == 1
    assert msgs[0]["role"] == "assistant"
    assert msgs[0]["content"] == [{"type": "text", "text": "reply"}]


def test_assistant_text_to_openai() -> None:
    """Produces assistant message with plain string content."""
    n = AssistantNode(id="2", text="reply")
    msgs = n.to_openai()
    assert msgs == [{"role": "assistant", "content": "reply"}]


def test_assistant_text_thinking_not_in_messages() -> None:
    """Thinking field is excluded from both provider messages."""
    n = AssistantNode(id="2", text="reply", thinking="secret thought")
    anthropic_msgs = n.to_anthropic()
    openai_msgs = n.to_openai()
    # thinking must not appear in converted messages
    assert "thinking" not in str(anthropic_msgs)
    assert "thinking" not in str(openai_msgs)


def test_assistant_text_empty_text() -> None:
    """Empty text still produces valid messages."""
    n = AssistantNode(id="2", text="")
    assert n.to_anthropic()[0]["content"] == [{"type": "text", "text": ""}]
    assert n.to_openai()[0]["content"] == ""


# ---------------------------------------------------------------------------
# AssistantNode (with tool_calls)
# ---------------------------------------------------------------------------


def test_assistant_tool_call_to_anthropic_basic() -> None:
    """Single tool call produces assistant message with tool_use block."""
    n = AssistantNode(
        id="3",
        tool_calls={"c1": {"tool_name": "bash", "arguments": {"cmd": "ls"}}},
    )
    msgs = n.to_anthropic()
    assert len(msgs) == 1
    msg = msgs[0]
    assert msg["role"] == "assistant"
    content = msg["content"]
    assert len(content) == 1
    assert content[0]["type"] == "tool_use"
    assert content[0]["id"] == "c1"
    assert content[0]["name"] == "bash"
    assert content[0]["input"] == {"cmd": "ls"}


def test_assistant_tool_call_to_anthropic_with_text() -> None:
    """Text prepended as text block before tool_use blocks."""
    n = AssistantNode(
        id="3",
        text="I'll run bash",
        tool_calls={"c1": {"tool_name": "bash", "arguments": {}}},
    )
    msgs = n.to_anthropic()
    content = msgs[0]["content"]
    assert content[0] == {"type": "text", "text": "I'll run bash"}
    assert content[1]["type"] == "tool_use"


def test_assistant_tool_call_to_anthropic_no_text() -> None:
    """Empty text omits text block."""
    n = AssistantNode(
        id="3",
        tool_calls={"c1": {"tool_name": "bash", "arguments": {}}},
    )
    msgs = n.to_anthropic()
    content = msgs[0]["content"]
    assert all(b["type"] != "text" for b in content)


def test_assistant_tool_call_to_openai_basic() -> None:
    """Single tool call produces assistant message with tool_calls list."""
    n = AssistantNode(
        id="3",
        tool_calls={"c1": {"tool_name": "bash", "arguments": {"cmd": "ls"}}},
    )
    msgs = n.to_openai()
    assert len(msgs) == 1
    msg = msgs[0]
    assert msg["role"] == "assistant"
    assert "content" not in msg
    tc = msg["tool_calls"]
    assert len(tc) == 1
    assert tc[0]["id"] == "c1"
    assert tc[0]["type"] == "function"
    assert tc[0]["function"]["name"] == "bash"
    assert json.loads(tc[0]["function"]["arguments"]) == {"cmd": "ls"}


def test_assistant_tool_call_to_openai_with_text() -> None:
    """Text becomes content field."""
    n = AssistantNode(
        id="3",
        text="thinking aloud",
        tool_calls={"c1": {"tool_name": "bash", "arguments": {}}},
    )
    msgs = n.to_openai()
    assert msgs[0].get("content") == "thinking aloud"


def test_assistant_tool_call_parallel_anthropic() -> None:
    """Multiple calls all appear as tool_use blocks in one message."""
    n = AssistantNode(
        id="3",
        tool_calls={
            "c1": {"tool_name": "bash", "arguments": {"cmd": "ls"}},
            "c2": {"tool_name": "echo", "arguments": {"text": "hi"}},
        },
    )
    msgs = n.to_anthropic()
    content = msgs[0]["content"]
    tool_use_blocks = [b for b in content if b["type"] == "tool_use"]
    assert len(tool_use_blocks) == 2


def test_assistant_tool_call_parallel_openai() -> None:
    """Multiple calls all appear in tool_calls list."""
    n = AssistantNode(
        id="3",
        tool_calls={
            "c1": {"tool_name": "bash", "arguments": {}},
            "c2": {"tool_name": "echo", "arguments": {}},
        },
    )
    msgs = n.to_openai()
    assert len(msgs[0]["tool_calls"]) == 2


# ---------------------------------------------------------------------------
# ToolResultNode
# ---------------------------------------------------------------------------


def test_tool_result_to_anthropic() -> None:
    """Produces user message with tool_result content block."""
    n = ToolResultNode(
        id="4",
        results={"c1": {"status": "completed", "content": "ok"}},
    )
    msgs = n.to_anthropic()
    assert len(msgs) == 1
    msg = msgs[0]
    assert msg["role"] == "user"
    blocks = msg["content"]
    assert len(blocks) == 1
    assert blocks[0]["type"] == "tool_result"
    assert blocks[0]["tool_use_id"] == "c1"
    assert "status: completed" in blocks[0]["content"]
    assert "content: ok" in blocks[0]["content"]


def test_tool_result_to_openai() -> None:
    """Produces one tool-role message per result."""
    n = ToolResultNode(
        id="4",
        results={
            "c1": {"status": "completed", "content": "out1"},
            "c2": {"status": "failed", "content": "err"},
        },
    )
    msgs = n.to_openai()
    assert len(msgs) == 2
    roles = {m["role"] for m in msgs}
    assert roles == {"tool"}
    call_ids = {m["tool_call_id"] for m in msgs}
    assert call_ids == {"c1", "c2"}


def test_tool_result_empty_results_anthropic() -> None:
    """Empty results produce a user message with empty content list."""
    n = ToolResultNode(id="4", results={})
    msgs = n.to_anthropic()
    assert msgs[0]["content"] == []


def test_tool_result_empty_results_openai() -> None:
    """Empty results produce an empty list."""
    n = ToolResultNode(id="4", results={})
    msgs = n.to_openai()
    assert msgs == []


def test_tool_result_non_string_content_formatted() -> None:
    """Non-string content values are JSON-serialized."""
    n = ToolResultNode(
        id="4",
        results={"c1": {"status": "completed", "content": {"key": "val"}}},
    )
    msgs = n.to_anthropic()
    text = msgs[0]["content"][0]["content"]
    assert '"key": "val"' in text
