"""CI integration tests: tool calls (bash, http, edit_file, mcp)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from little_agent.agent.agent import AgentCore
from little_agent.agent.nodes import ToolResultNode
from little_agent.agent.permissions import YesManChecker
from little_agent.tools.file import EditFileToolProvider
from little_agent.tools.http import HttpToolProvider
from little_agent.tools.manager import ToolManager
from little_agent.tools.mcp import MCPStdioProvider
from tests.mocks import MockClient

from .helpers import build_agent, make_backend, walk_chain

_MOCK_MCP_SERVER = str(Path(__file__).parent.parent / "tests" / "fixtures" / "mock_mcp_server.py")

pytestmark = [pytest.mark.ci, pytest.mark.timeout(120)]


@pytest.mark.asyncio
async def test_bash_tool(ci_config: dict[str, Any]) -> None:
    """Ask the agent to run a bash command and verify the tool was executed."""
    agent, client = build_agent(ci_config)
    session = await agent.new()

    reason, text = await session.prompt(
        "Use the bash tool to run the command `echo ci-test-marker` and report the output."
    )

    assert reason == "end_turn", f"Unexpected stop reason: {reason}"
    assert text.strip(), "Response should not be empty"

    chain = walk_chain(session)
    tool_results = [n for n in chain if isinstance(n, ToolResultNode)]
    assert tool_results, "Expected at least one tool call to have executed"

    bash_ran = any("ci-test-marker" in str(r.results) for r in tool_results)
    assert bash_ran, "bash tool should have produced 'ci-test-marker' in its output"


@pytest.mark.asyncio
async def test_http_tool(ci_config: dict[str, Any]) -> None:
    """Ask the agent to use the http tool and verify status=200."""
    backend = make_backend(ci_config)
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

    chain = walk_chain(session)
    tool_results = [n for n in chain if isinstance(n, ToolResultNode)]
    assert tool_results, "Expected at least one http tool call"

    found_200 = any(
        isinstance(result.get("content"), dict) and result["content"].get("status") == 200
        for r in tool_results
        for result in r.results.values()
    )
    assert found_200, "http tool should have returned status=200"


@pytest.mark.asyncio
async def test_edit_file_tool(ci_config: dict[str, Any], tmp_path: Path) -> None:
    """Ask the agent to create a temp file and verify content exists."""
    backend = make_backend(ci_config)
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

    chain = walk_chain(session)
    tool_results = [n for n in chain if isinstance(n, ToolResultNode)]
    assert tool_results, "Expected at least one edit_file tool call"

    assert target_file.exists(), f"File should have been created: {target_file}"
    content = target_file.read_text(encoding="utf-8")
    assert sentinel in content, f"File content should include sentinel: {sentinel}"


@pytest.mark.asyncio
async def test_mcp_tool(ci_config: dict[str, Any]) -> None:
    """Start a local MCP subprocess and verify the agent can invoke its echo tool."""
    backend = make_backend(ci_config)
    provider = MCPStdioProvider(name="testmcp", command=[sys.executable, _MOCK_MCP_SERVER])
    await provider.start()
    try:
        tools = ToolManager()
        tools.register(provider)
        client: MockClient = MockClient()
        agent = AgentCore(
            client=client, backend=backend, tools=tools, permissions=YesManChecker()
        )
        session = await agent.new()

        sentinel = "mcp-ci-sentinel"
        reason, _text = await session.prompt(
            f"Use the testmcp__echo tool with text='{sentinel}' and report the result."
        )

        assert reason == "end_turn"

        chain = walk_chain(session)
        tool_results = [n for n in chain if isinstance(n, ToolResultNode)]
        assert tool_results, "Expected at least one MCP tool call"

        found = any(sentinel in str(r.results) for r in tool_results)
        assert found, f"MCP echo tool should have returned '{sentinel}' in results"
    finally:
        await provider.stop()
