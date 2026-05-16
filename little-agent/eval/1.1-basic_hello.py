"""1.1 Hello World: single prompt, single reply — baseline sanity check."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
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

REPEATS = 3
PROMPT = "What is 1 + 1?"
EXPECTED = "2"


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
        client=_NullClient(), backend=backend, tools=ToolManager(),
        permissions=YesManChecker(), ignore_agentsmd=True,
    )


def _extract_output(session: Any) -> str:
    for node in reversed(session.messages):
        if isinstance(node, AssistantNode) and node.text:
            return node.text
    return ""


async def _run(config: dict[str, Any]) -> bool:
    print("=== 1.1 Hello World ===")
    all_pass = True
    for i in range(1, REPEATS + 1):
        agent = _build_agent(config)
        session = await agent.new()
        await session.prompt(PROMPT)
        output = _extract_output(session)
        correct = bool(output.strip()) and EXPECTED in output
        status = "PASS" if correct else "FAIL"
        if not correct:
            all_pass = False
        print(f"  run{i}: {status}  output=\"{output.replace(chr(10), ' ')[:80]}\"")
    print(f"result: {'3/3 PASS' if all_pass else 'FAIL'}")
    return all_pass


def main() -> None:
    parser = argparse.ArgumentParser(description="1.1 hello world (3 calls)")
    parser.add_argument("--config",
                        default=str(Path.home() / ".config/little_agent/config.yaml"))
    parser.add_argument("--loglevel", default="WARNING")
    args = parser.parse_args()
    logging.basicConfig(level=args.loglevel.upper())
    ok = asyncio.run(_run(_load_config(args.config)))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
