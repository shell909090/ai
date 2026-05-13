"""Tests for agent.load() schema validation."""

from __future__ import annotations

import json

import pytest

from little_agent.agent.agent import AgentCore, _validate_messages
from little_agent.agent.nodes import validate_node_dict
from little_agent.agent.tool_manager import ToolManager
from little_agent.backends.protocol import BackendTurnResult
from tests.mocks import MockBackend, MockClient


def _make_agent() -> AgentCore:
    client = MockClient()
    backend = MockBackend(
        script=[BackendTurnResult(output_text="ok", tool_calls=[], finish_reason="completed")]
    )
    tools = ToolManager()
    return AgentCore(client=client, backend=backend, tools=tools)


# ---------------------------------------------------------------------------
# validate_node_dict tests
# ---------------------------------------------------------------------------


def test_validate_node_dict_missing_id() -> None:
    """validate_node_dict raises on missing 'id'."""
    with pytest.raises(ValueError, match="id"):
        validate_node_dict({"kind": "user_prompt"})


def test_validate_node_dict_missing_kind() -> None:
    """validate_node_dict raises on missing 'kind'."""
    with pytest.raises(ValueError, match="kind"):
        validate_node_dict({"id": "n1"})


def test_validate_node_dict_unknown_kind() -> None:
    """validate_node_dict raises on unknown kind."""
    with pytest.raises(ValueError, match="unknown node kind"):
        validate_node_dict({"id": "n1", "kind": "mystery_node"})


def test_validate_node_dict_wrong_type_calls() -> None:
    """validate_node_dict raises when 'tool_calls' is not a dict for assistant."""
    with pytest.raises(ValueError, match="tool_calls"):
        validate_node_dict({"id": "n1", "kind": "assistant", "tool_calls": "bad"})


def test_validate_node_dict_wrong_type_results() -> None:
    """validate_node_dict raises when 'results' is not a dict for tool_result."""
    with pytest.raises(ValueError, match="results"):
        validate_node_dict({"id": "n1", "kind": "tool_result", "results": [1, 2]})


def test_validate_node_dict_valid_user_prompt() -> None:
    """validate_node_dict accepts a valid user_prompt node."""
    validate_node_dict({"id": "n1", "kind": "user_prompt", "prompt": "hello"})


def test_validate_node_dict_valid_tool_call() -> None:
    """validate_node_dict accepts a valid assistant node."""
    validate_node_dict({"id": "n1", "kind": "assistant"})


def test_validate_node_dict_not_a_dict() -> None:
    """validate_node_dict raises when input is not a dict."""
    with pytest.raises(ValueError, match="must be a dict"):
        validate_node_dict("bad")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _validate_messages tests
# ---------------------------------------------------------------------------


def test_validate_messages_duplicate_ids() -> None:
    """_validate_messages raises on duplicate node IDs."""
    messages = [
        {"id": "n1", "kind": "user_prompt", "prompt": "hello"},
        {"id": "n1", "kind": "user_prompt", "prompt": "again"},
    ]
    with pytest.raises(ValueError, match="duplicate node id"):
        _validate_messages(messages)


def test_validate_messages_non_dict_item() -> None:
    """_validate_messages raises when an item is not a dict."""
    with pytest.raises(ValueError, match="must be a dict"):
        _validate_messages(["not a dict"])


def test_validate_messages_valid() -> None:
    """_validate_messages passes for a well-formed messages list."""
    messages = [
        {"id": "n1", "kind": "user_prompt", "prompt": "hello"},
        {"id": "n2", "kind": "assistant", "text": "hi"},
    ]
    _validate_messages(messages)  # must not raise


# ---------------------------------------------------------------------------
# agent.load() round-trip and error tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_load_valid_round_trip() -> None:
    """agent.load() accepts valid serialized session data."""
    agent = _make_agent()
    data: dict = {
        "id": "test-session-id",
        "cwd": None,
        "system_prompt": None,
        "summaries": [],
        "messages": [
            {"id": "n1", "kind": "user_prompt", "prompt": "hello"},
            {"id": "n2", "kind": "assistant", "text": "hi"},
        ],
    }
    session = await agent.load(data)
    assert session.id == "test-session-id"
    assert len(session.messages) > 0
    assert session.messages[-1].id == "n2"


@pytest.mark.asyncio
async def test_agent_load_missing_id_raises() -> None:
    """agent.load() raises ValueError on missing session id."""
    agent = _make_agent()
    with pytest.raises(ValueError, match="id"):
        await agent.load({"messages": []})


@pytest.mark.asyncio
async def test_agent_load_bad_node_kind_raises() -> None:
    """agent.load() raises ValueError on unknown node kind."""
    agent = _make_agent()
    data = {
        "id": "s1",
        "cwd": None,
        "messages": [{"id": "n1", "kind": "unknown_kind"}],
    }
    with pytest.raises(ValueError, match="unknown node kind"):
        await agent.load(data)


@pytest.mark.asyncio
async def test_agent_load_duplicate_ids_raises() -> None:
    """agent.load() raises ValueError on duplicate node IDs."""
    agent = _make_agent()
    data = {
        "id": "s1",
        "cwd": None,
        "messages": [
            {"id": "n1", "kind": "user_prompt", "prompt": "a"},
            {"id": "n1", "kind": "user_prompt", "prompt": "b"},
        ],
    }
    with pytest.raises(ValueError, match="duplicate node id"):
        await agent.load(data)


@pytest.mark.asyncio
async def test_agent_load_bad_calls_type_raises() -> None:
    """agent.load() raises ValueError when assistant.tool_calls is not a dict."""
    agent = _make_agent()
    data = {
        "id": "s1",
        "cwd": None,
        "messages": [
            {"id": "n1", "kind": "assistant", "tool_calls": "not-a-dict"},
        ],
    }
    with pytest.raises(ValueError):
        await agent.load(data)


@pytest.mark.asyncio
async def test_agent_load_empty_messages() -> None:
    """agent.load() accepts empty messages and returns session with no messages."""
    agent = _make_agent()
    data = {"id": "s1", "cwd": None, "messages": []}
    session = await agent.load(data)
    assert len(session.messages) == 0


@pytest.mark.asyncio
async def test_agent_save_load_round_trip() -> None:
    """save() → load() round-trip produces equivalent session."""
    agent = _make_agent()
    session = await agent.new()
    session_data = session.save()
    loaded = await agent.load(session_data)
    assert loaded.id == session.id
    assert loaded.cwd == session.cwd


@pytest.mark.asyncio
async def test_cli_load_catches_value_error(capsys: pytest.CaptureFixture[str]) -> None:
    """CLI _do_load prints an error on ValueError without raising."""
    from little_agent.frontends.cli import CliClient

    agent = _make_agent()
    session = await agent.new()
    cli = CliClient.__new__(CliClient)
    cli._buffer_type = None
    cli._buffer_parts = []

    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"id": "s1", "cwd": None, "messages": [{"id": "n1", "kind": "bad_kind"}]}, f)
        tmp_path = f.name

    from pathlib import Path

    new_session, ok = await cli._do_load(agent, session, Path(tmp_path))
    assert not ok
    assert new_session is session
    captured = capsys.readouterr()
    assert "[Error]" in captured.out
