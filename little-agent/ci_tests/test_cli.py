"""CI integration tests: CLI frontend commands."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from little_agent.agent.agent import AgentCore
from little_agent.agent.compressor import LLMCompressor
from little_agent.agent.nodes import SummaryNode
from little_agent.agent.permissions import YesManChecker
from little_agent.frontends.cli import CliClient
from little_agent.tools.bash import BashToolProvider
from little_agent.agent.tool_manager import ToolManager

from .helpers import make_backend, walk_chain

pytestmark = [pytest.mark.ci, pytest.mark.timeout(120)]


@pytest.mark.asyncio
async def test_new_command(ci_config: dict[str, Any]) -> None:
    """Complete one turn, call /new, verify the new session has a different id."""
    backend = make_backend(ci_config)
    tools = ToolManager()
    tools.register(BashToolProvider())
    cli_client = CliClient()
    agent = AgentCore(client=cli_client, backend=backend, tools=tools, permissions=YesManChecker())
    session = await agent.new()
    original_id = session.id

    reason, _ = await session.prompt("Say just: hello")
    assert reason == "end_turn"

    new_session, should_continue = await cli_client._handle_command(agent, session, "/new")
    assert should_continue is True
    assert new_session.id != original_id, "/new should produce a session with a different id"


@pytest.mark.asyncio
async def test_fork_command(ci_config: dict[str, Any]) -> None:
    """Complete one turn, call /fork, verify forked session shares history but has different id."""
    backend = make_backend(ci_config)
    tools = ToolManager()
    tools.register(BashToolProvider())
    cli_client = CliClient()
    agent = AgentCore(client=cli_client, backend=backend, tools=tools, permissions=YesManChecker())
    session = await agent.new()
    original_id = session.id

    reason, _ = await session.prompt("Say just: hello")
    assert reason == "end_turn"

    forked_session, should_continue = await cli_client._handle_command(agent, session, "/fork")
    assert should_continue is True
    assert forked_session.id != original_id, "Forked session must have a different id"

    original_node_ids = {n.id for n in walk_chain(session)}
    forked_node_ids = {n.id for n in walk_chain(forked_session)}
    assert original_node_ids & forked_node_ids, "Forked session should share history nodes"


@pytest.mark.asyncio
async def test_save_load(ci_config: dict[str, Any], tmp_path: Path) -> None:
    """Save session to a file, load it, verify tail node id matches."""
    backend = make_backend(ci_config)
    tools = ToolManager()
    tools.register(BashToolProvider())
    cli_client = CliClient()
    agent = AgentCore(client=cli_client, backend=backend, tools=tools, permissions=YesManChecker())
    session: Any = await agent.new()

    reason, _ = await session.prompt("Say just: hello")
    assert reason == "end_turn"
    original_tail_id = session.tail.id if session.tail else None

    save_path = tmp_path / "session_b3.json"
    await cli_client._do_save(session, save_path)
    assert save_path.exists(), "Session save file should exist"

    loaded_session: Any
    loaded_session, ok = await cli_client._do_load(agent, session, save_path)
    assert ok is True, "Session load should succeed"

    loaded_tail_id = loaded_session.tail.id if loaded_session.tail else None
    assert loaded_tail_id == original_tail_id, "Loaded session tail should match original"


@pytest.mark.asyncio
async def test_compact_cli(ci_config: dict[str, Any]) -> None:
    """Inject compressor, do 3 turns, call /compact, verify SummaryNode in chain."""
    backend = make_backend(ci_config)
    tools = ToolManager()
    tools.register(BashToolProvider())
    compressor = LLMCompressor(backend, keep_turns=1, compressed_window_tokens=0)
    cli_client = CliClient()
    agent = AgentCore(
        client=cli_client,
        backend=backend,
        tools=tools,
        compressor=compressor,
        permissions=YesManChecker(),
    )
    session = await agent.new()

    for prompt_text in ("Say: one", "Say: two", "Say: three"):
        reason, _ = await session.prompt(prompt_text)
        assert reason == "end_turn"

    await cli_client._do_compact(session)

    chain = walk_chain(session)
    assert any(isinstance(n, SummaryNode) for n in chain), (
        "After /compact with keep_turns=1 and 3 turns, a SummaryNode must appear"
    )
