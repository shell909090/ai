"""CI integration tests using a real AI backend.

Config is loaded from --ci-config (default: ~/.config/little_agent/config.yaml).
All tests are marked `ci` and skipped when the config file is absent.
Run with: make ci-test
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

from little_agent.agent.agent import AgentCore
from little_agent.agent.compressor import LLMCompressor
from little_agent.agent.nodes import SummaryNode, ToolResultNode
from little_agent.agent.permissions import BlackWhiteListChecker, YesManChecker
from little_agent.agent.session_store import SessionJSONLStore
from little_agent.backends.build import _DEFAULT_BACKEND_CONFIG, _build_backend
from little_agent.frontends.cli import CliClient
from little_agent.frontends.web.client import WebClient
from little_agent.frontends.web.handlers import (
    do_session_compact,
    do_session_new,
    do_session_prompt,
)
from little_agent.main import _DEFAULT_CONFIG, _deep_merge
from little_agent.tools.bash import BashToolProvider
from little_agent.tools.file import EditFileToolProvider
from little_agent.tools.http import HttpToolProvider
from little_agent.tools.manager import ToolManager
from tests.mocks import MockClient

pytestmark = [pytest.mark.ci, pytest.mark.timeout(120)]


@pytest.fixture(scope="session")
def ci_config(ci_config_path: Path) -> dict[str, Any]:
    """Load CI backend config; skip entire session if config file is missing."""
    if not ci_config_path.exists():
        pytest.skip(f"CI config not found at {ci_config_path}; skipping CI tests")
    with open(ci_config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        pytest.skip(f"CI config at {ci_config_path} is not a YAML mapping")
    return _deep_merge(_DEFAULT_CONFIG, data)


def _make_backend(config: dict[str, Any]) -> Any:
    """Build primary backend from merged config."""
    backends_cfg = config.get("backends", {})
    primary_cfg = backends_cfg.get("primary", {})
    if not isinstance(primary_cfg, dict):
        pytest.skip("backends.primary missing in CI config")
    return _build_backend(_deep_merge(_DEFAULT_BACKEND_CONFIG, primary_cfg), "primary")


def _build_agent(config: dict[str, Any]) -> tuple[AgentCore, MockClient]:
    """Build an AgentCore from config with real backend and bash tool."""
    backend = _make_backend(config)
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


def _walk_chain(session: Any) -> list[Any]:
    """Return all nodes in the chain from tail back to head."""
    nodes = []
    node = session.tail
    while node is not None:
        nodes.append(node)
        node = node.prev
    return nodes


def _make_ws_mock() -> MagicMock:
    """Create a minimal WebSocket mock with async send methods."""
    ws = MagicMock()
    ws.send_str = AsyncMock()
    ws.send_json = AsyncMock()
    return ws


# ---------------------------------------------------------------------------
# A. Basic conversation and tool calls
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a1_basic_conversation(ci_config: dict[str, Any]) -> None:
    """Send a simple prompt and verify a successful end_turn response."""
    agent, client = _build_agent(ci_config)
    session = await agent.new()

    reason, text = await session.prompt("Reply with exactly the word: hello")

    assert reason == "end_turn", f"Unexpected stop reason: {reason}"
    assert text.strip(), "Response should not be empty"
    assert len(client.updates) > 0, "Should have received at least one update"


@pytest.mark.asyncio
async def test_a2_bash_tool(ci_config: dict[str, Any]) -> None:
    """Ask the agent to run a bash command and verify the tool was executed."""
    agent, client = _build_agent(ci_config)
    session = await agent.new()

    reason, text = await session.prompt(
        "Use the bash tool to run the command `echo ci-test-marker` and report the output."
    )

    assert reason == "end_turn", f"Unexpected stop reason: {reason}"
    assert text.strip(), "Response should not be empty"

    chain = _walk_chain(session)
    tool_results = [n for n in chain if isinstance(n, ToolResultNode)]
    assert tool_results, "Expected at least one tool call to have executed"

    bash_ran = any("ci-test-marker" in str(r.results) for r in tool_results)
    assert bash_ran, "bash tool should have produced 'ci-test-marker' in its output"


@pytest.mark.asyncio
async def test_a3_http_tool(ci_config: dict[str, Any]) -> None:
    """Ask the agent to use the http tool and verify status=200."""
    backend = _make_backend(ci_config)
    tools = ToolManager()
    tools.register(HttpToolProvider())
    client: MockClient = MockClient()
    agent = AgentCore(client=client, backend=backend, tools=tools, permissions=YesManChecker())
    session = await agent.new()

    reason, _text = await session.prompt(
        "Use the http tool to send a GET request to http://httpbin.org/get "
        "and tell me the HTTP status code you received."
    )

    assert reason == "end_turn"

    chain = _walk_chain(session)
    tool_results = [n for n in chain if isinstance(n, ToolResultNode)]
    assert tool_results, "Expected at least one http tool call"

    found_200 = any(
        isinstance(result.get("content"), dict) and result["content"].get("status") == 200
        for r in tool_results
        for result in r.results.values()
    )
    assert found_200, "http tool should have returned status=200"


@pytest.mark.asyncio
async def test_a4_edit_file_tool(ci_config: dict[str, Any], tmp_path: Path) -> None:
    """Ask the agent to create a temp file and verify content exists."""
    backend = _make_backend(ci_config)
    tools = ToolManager()
    tools.register(EditFileToolProvider())
    client: MockClient = MockClient()
    agent = AgentCore(client=client, backend=backend, tools=tools, permissions=YesManChecker())
    session = await agent.new()

    target_file = tmp_path / "ci_test_output.txt"
    sentinel = "ci-file-sentinel-xk9m2"

    reason, _text = await session.prompt(
        f"Use the edit_file tool to create the file '{target_file}' "
        f"with create=true containing the text: {sentinel}"
    )

    assert reason == "end_turn"

    chain = _walk_chain(session)
    tool_results = [n for n in chain if isinstance(n, ToolResultNode)]
    assert tool_results, "Expected at least one edit_file tool call"

    assert target_file.exists(), f"File should have been created: {target_file}"
    content = target_file.read_text(encoding="utf-8")
    assert sentinel in content, f"File content should include sentinel: {sentinel}"


# ---------------------------------------------------------------------------
# B. CLI frontend commands (via CliClient + AgentCore, no subprocess)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_b1_new_command(ci_config: dict[str, Any]) -> None:
    """Complete one turn, call /new, verify the new session has a different id."""
    backend = _make_backend(ci_config)
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
async def test_b2_fork_command(ci_config: dict[str, Any]) -> None:
    """Complete one turn, call /fork, verify forked session shares history but has different id."""
    backend = _make_backend(ci_config)
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

    original_node_ids = {n.id for n in _walk_chain(session)}
    forked_node_ids = {n.id for n in _walk_chain(forked_session)}
    assert original_node_ids & forked_node_ids, "Forked session should share history nodes"


@pytest.mark.asyncio
async def test_b3_save_load(ci_config: dict[str, Any], tmp_path: Path) -> None:
    """Save session to a file, load it, verify tail node id matches."""
    backend = _make_backend(ci_config)
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
async def test_b4_compact_cli(ci_config: dict[str, Any]) -> None:
    """Inject compressor, do 3 turns, call /compact, verify SummaryNode in chain."""
    backend = _make_backend(ci_config)
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

    chain = _walk_chain(session)
    assert any(isinstance(n, SummaryNode) for n in chain), (
        "After /compact with keep_turns=1 and 3 turns, a SummaryNode must appear"
    )


# ---------------------------------------------------------------------------
# C. Web frontend commands (via WebSocket handler functions)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_c1_web_session_prompt(ci_config: dict[str, Any], tmp_path: Path) -> None:
    """session/new then session/prompt via handler functions; verify prompt_response."""
    backend = _make_backend(ci_config)
    tools = ToolManager()
    tools.register(BashToolProvider())
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    web_client = WebClient(sessions_dir=sessions_dir)
    agent = AgentCore(
        client=web_client, backend=backend, tools=tools, permissions=YesManChecker()
    )

    ws = _make_ws_mock()
    web_client.add_websocket(ws)

    new_resp = await do_session_new(web_client, agent, ws, {"type": "session/new"})
    assert new_resp is not None
    assert new_resp.get("type") == "session/new_response"
    session_id = new_resp.get("session_id")
    assert isinstance(session_id, str) and session_id

    prompt_resp = await do_session_prompt(
        web_client,
        agent,
        ws,
        {"type": "session/prompt", "session_id": session_id, "prompt": "Say: hello"},
    )
    assert prompt_resp is not None
    assert prompt_resp.get("type") == "session/prompt_response"
    assert prompt_resp.get("stop_reason") == "end_turn"


@pytest.mark.asyncio
async def test_c2_web_compact(ci_config: dict[str, Any], tmp_path: Path) -> None:
    """Do 3 turns via web handlers then session/compact; verify ok=True and SummaryNode."""
    backend = _make_backend(ci_config)
    tools = ToolManager()
    tools.register(BashToolProvider())
    compressor = LLMCompressor(backend, keep_turns=1, compressed_window_tokens=0)
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    web_client = WebClient(sessions_dir=sessions_dir)
    agent = AgentCore(
        client=web_client,
        backend=backend,
        tools=tools,
        compressor=compressor,
        permissions=YesManChecker(),
    )

    ws = _make_ws_mock()
    web_client.add_websocket(ws)

    new_resp = await do_session_new(web_client, agent, ws, {"type": "session/new"})
    assert new_resp is not None
    session_id = str(new_resp["session_id"])

    for text in ("Say: one", "Say: two", "Say: three"):
        await do_session_prompt(
            web_client, agent, ws,
            {"type": "session/prompt", "session_id": session_id, "prompt": text},
        )

    compact_resp = await do_session_compact(
        web_client, agent, ws,
        {"type": "session/compact", "session_id": session_id},
    )
    assert compact_resp is not None
    assert compact_resp.get("type") == "session/compact_response"
    assert compact_resp.get("ok") is True, f"compact failed: {compact_resp.get('error')}"

    sess = web_client.store.get_session(session_id)
    assert sess is not None
    chain = _walk_chain(sess)
    assert any(isinstance(n, SummaryNode) for n in chain), (
        "After web compact, chain must contain a SummaryNode"
    )


# ---------------------------------------------------------------------------
# D. Compressor scenario
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_d1_auto_compression(ci_config: dict[str, Any]) -> None:
    """With compress_ratio=1e-6, verify SummaryNode appears after 2 turns."""
    backend = _make_backend(ci_config)
    tools = ToolManager()
    tools.register(BashToolProvider())
    compressor = LLMCompressor(backend, keep_turns=1, compressed_window_tokens=0)
    client: MockClient = MockClient()
    agent = AgentCore(
        client=client,
        backend=backend,
        tools=tools,
        compressor=compressor,
        permissions=YesManChecker(),
        # 1e-6 << any realistic token/char ratio, so every turn triggers auto-compress.
        compress_ratio=1e-6,
    )
    session: Any = await agent.new()

    reason1, _ = await session.prompt("Say: one")
    assert reason1 == "end_turn"
    compress_task = getattr(session, "compress_task", None)
    if compress_task is not None:
        await compress_task

    reason2, _ = await session.prompt("Say: two")
    assert reason2 == "end_turn"
    compress_task = getattr(session, "compress_task", None)
    if compress_task is not None:
        await compress_task

    chain = _walk_chain(session)
    assert any(isinstance(n, SummaryNode) for n in chain), (
        "With compress_ratio=1e-6 and 2 turns, a SummaryNode should appear after auto-compress"
    )


# ---------------------------------------------------------------------------
# E. Permission scenario
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e1_blackwhitelist_deny(ci_config: dict[str, Any]) -> None:
    """Blacklist bash; verify bash tool result has status=failed and 'Permission denied'."""
    backend = _make_backend(ci_config)
    tools = ToolManager()
    tools.register(BashToolProvider())
    permissions = BlackWhiteListChecker(
        blacklist=["bash"], whitelist=[], next_checker=YesManChecker()
    )
    client: MockClient = MockClient()
    agent = AgentCore(client=client, backend=backend, tools=tools, permissions=permissions)
    session = await agent.new()

    reason, _text = await session.prompt(
        "You MUST call the bash tool to run `echo denied-test`. "
        "Call it even if you expect it to fail."
    )

    assert reason == "end_turn"

    chain = _walk_chain(session)
    tool_results = [n for n in chain if isinstance(n, ToolResultNode)]
    assert tool_results, "AI should have attempted the bash tool call"

    denied = any(
        result.get("status") == "failed"
        and "Permission denied" in str(result.get("content", ""))
        for r in tool_results
        for result in r.results.values()
    )
    assert denied, "bash tool result should be failed with 'Permission denied'"


# ---------------------------------------------------------------------------
# F. compact + search_session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_f1_compact_search_session(ci_config: dict[str, Any], tmp_path: Path) -> None:
    """After compacting session with keyword in turn 1, search_session still finds it."""
    backend = _make_backend(ci_config)
    keyword = "f1-unique-keyword-zq7r9"
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()

    store = SessionJSONLStore(sessions_dir=str(sessions_dir))
    tools = ToolManager()
    tools.register(BashToolProvider())
    tools.register(store)

    compressor = LLMCompressor(backend, keep_turns=1, compressed_window_tokens=0)
    client: MockClient = MockClient()
    agent = AgentCore(
        client=client,
        backend=backend,
        tools=tools,
        compressor=compressor,
        hooks=[store],
        permissions=YesManChecker(),
    )
    session = await agent.new()

    reason1, _ = await session.prompt(
        f"Remember this unique identifier: {keyword}. Just say OK."
    )
    assert reason1 == "end_turn"

    reason2, _ = await session.prompt("Say: two")
    assert reason2 == "end_turn"
    reason3, _ = await session.prompt("Say: three")
    assert reason3 == "end_turn"

    await session.compress()
    chain = _walk_chain(session)
    assert any(isinstance(n, SummaryNode) for n in chain), (
        "Chain should contain SummaryNode after compress"
    )

    reason4, _text4 = await session.prompt(
        f"Use the search_session tool to search for '{keyword}'. Report what you find."
    )
    assert reason4 == "end_turn"

    chain4 = _walk_chain(session)
    tool_results = [n for n in chain4 if isinstance(n, ToolResultNode)]
    found_keyword = any(keyword in str(r.results) for r in tool_results)
    assert found_keyword, (
        f"search_session result should contain '{keyword}' from compressed JSONL history"
    )
