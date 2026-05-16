"""1.2 Basic tool call: verify that a prompt can induce at least one tool invocation."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from little_agent._utils import _deep_merge
from little_agent.agent.agent import AgentCore
from little_agent.agent.nodes import AssistantNode
from little_agent.agent.permissions import YesManChecker
from little_agent.agent.tool_manager import ToolManager
from little_agent.backends.build import _DEFAULT_BACKEND_CONFIG, _build_backend
from little_agent.tools.protocol import ToolArgDef, ToolDef
from little_agent.types import JSONValue, Session

REPEATS = 3
PROMPT = "What does the file /etc/hosts contain?"
MOCK_CONTENT = "127.0.0.1   localhost\n127.0.1.1   myhost\n::1         localhost"


@dataclass
class _ToolSpec:
    name: str
    desc: str
    args: list[ToolArgDef] = field(default_factory=list)


class _MockProvider:
    def __init__(self, spec: _ToolSpec) -> None:
        self._spec = spec

    def __iter__(self):
        spec = self._spec

        async def _fn(_args: Any, _session: Session) -> JSONValue:
            return {"status": "completed", "content": MOCK_CONTENT}

        yield spec.name, ToolDef(desc=spec.desc, args=spec.args), _fn


def _build_tools() -> ToolManager:
    tm = ToolManager()
    tm.register(_MockProvider(_ToolSpec(
        "read", "Read the contents of a file",
        [ToolArgDef("path", "string", "Absolute path to the file", True)],
    )))
    tm.register(_MockProvider(_ToolSpec(
        "bash", "Execute a shell command and return stdout/stderr",
        [ToolArgDef("command", "string", "The shell command to execute", True)],
    )))
    return tm


def _load_config(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


class _NullClient:
    async def update(self, _s: Any, _u: Any) -> None:
        pass

    async def check_permission(self, _s: Any, _t: str, _a: Any) -> bool:
        return True


def _build_agent(config: dict[str, Any]) -> AgentCore:
    primary_cfg = config.get("backends", {}).get("primary", {})
    backend = _build_backend(_deep_merge(_DEFAULT_BACKEND_CONFIG, primary_cfg), "primary")
    return AgentCore(
        client=_NullClient(), backend=backend, tools=_build_tools(),
        permissions=YesManChecker(), ignore_agentsmd=True,
        max_tool_result_chars=200,
    )


def _extract_tool_called(session: Any) -> tuple[bool, str]:
    for node in session.messages:
        if not isinstance(node, AssistantNode) or not node.tool_calls:
            continue
        first = next(iter(node.tool_calls.values()))
        return True, first["tool_name"]
    return False, ""


async def _run(config: dict[str, Any]) -> bool:
    print("=== 1.2 Basic Tool Call ===")
    all_pass = True
    for i in range(1, REPEATS + 1):
        agent = _build_agent(config)
        session = await agent.new()
        await session.prompt(PROMPT)
        called, tool_name = _extract_tool_called(session)
        status = "PASS" if called else "FAIL"
        if not called:
            all_pass = False
        detail = f"tool={tool_name}" if called else "tool=none"
        print(f"  run{i}: {status}  {detail}")
    print(f"result: {'3/3 PASS' if all_pass else 'FAIL'}")
    return all_pass


def main() -> None:
    parser = argparse.ArgumentParser(description="1.2 basic tool call (3 calls)")
    parser.add_argument("--config",
                        default=str(Path.home() / ".config/little_agent/config.yaml"))
    parser.add_argument("--loglevel", default="WARNING")
    args = parser.parse_args()
    logging.basicConfig(level=args.loglevel.upper())
    ok = asyncio.run(_run(_load_config(args.config)))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
