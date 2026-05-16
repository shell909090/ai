"""1.3 Tool call intent gradient: measure how prompt clarity affects tool invocation rate."""

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

REPEATS = 5

_ETC_HOSTS_MOCK = "127.0.0.1   localhost\n127.0.1.1   myhost\n::1         localhost"

SP_WEAK = "You have access to tools. Use them when appropriate."
SP_STRONG = (
    "When users ask about file contents or system configuration, always use the"
    " available tools to retrieve accurate information rather than guessing."
)

L1 = "Use the read tool to show me the contents of /etc/hosts."
L2 = "What does the file /etc/hosts contain?"
L3 = "How is hostname resolution configured on this system?"

GROUPS: list[tuple[str, str | None, str, str]] = [
    ("M1", None,      "L1", L1),
    ("M2", None,      "L2", L2),
    ("M3", None,      "L3", L3),
    ("M4", SP_WEAK,   "L2", L2),
    ("M5", SP_WEAK,   "L3", L3),
    ("M6", SP_STRONG, "L2", L2),
    ("M7", SP_STRONG, "L3", L3),
]

_SP_LABEL: dict[str | None, str] = {
    None: "none",
    SP_WEAK: "SP-weak",
    SP_STRONG: "SP-strong",
}


@dataclass
class ToolSpec:
    """Tool spec for mock provider."""

    name: str
    desc: str
    args: list[ToolArgDef] = field(default_factory=list)


class _ContentMockProvider:
    """Mock provider that returns fixed content."""

    def __init__(self, spec: ToolSpec, content: str) -> None:
        self._spec = spec
        self._content = content

    def __iter__(self):
        spec = self._spec
        content = self._content

        async def _fn(_args: Any, _session: Session) -> JSONValue:
            return {"status": "completed", "content": content}

        yield spec.name, ToolDef(desc=spec.desc, args=spec.args), _fn


def _build_tools() -> ToolManager:
    tm = ToolManager()
    tm.register(_ContentMockProvider(
        ToolSpec("read", "Read the contents of a file",
                 [ToolArgDef("path", "string", "Absolute path to the file", True)]),
        _ETC_HOSTS_MOCK,
    ))
    tm.register(_ContentMockProvider(
        ToolSpec("bash", "Execute a shell command and return stdout/stderr",
                 [ToolArgDef("command", "string", "The shell command to execute", True)]),
        _ETC_HOSTS_MOCK,
    ))
    return tm


def _load_config(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


class _NullClient:
    async def update(self, _session: Any, _update: Any) -> None:
        pass

    async def check_permission(self, _session: Any, _tool: str, _args: Any) -> bool:
        return True


def _build_agent(config: dict[str, Any], tools: ToolManager,
                 system_prompt: str | None = None) -> AgentCore:
    primary_cfg = config.get("backends", {}).get("primary", {})
    backend = _build_backend(_deep_merge(_DEFAULT_BACKEND_CONFIG, primary_cfg), "primary")
    return AgentCore(
        client=_NullClient(), backend=backend, tools=tools,
        permissions=YesManChecker(), ignore_agentsmd=True,
        max_tool_result_chars=200, system_prompt=system_prompt,
    )


def _extract_tool_called(session: Any) -> tuple[bool, str]:
    """Return (tool_called, tool_name) from the first real assistant tool call."""
    for node in session.messages:
        if not isinstance(node, AssistantNode) or not node.tool_calls:
            continue
        if any(tc["tool_name"].startswith("hist") for tc in node.tool_calls.values()):
            continue
        first_call = next(iter(node.tool_calls.values()))
        return True, first_call["tool_name"]
    return False, ""


async def _run(config: dict[str, Any]) -> None:
    print("=== 1.3 工具调用意图梯度 ===")
    for label, sp, up_label, user_prompt in GROUPS:
        sp_label = _SP_LABEL[sp]
        run_parts: list[str] = []
        call_count = 0
        for run_idx in range(1, REPEATS + 1):
            tools = _build_tools()
            agent = _build_agent(config, tools, system_prompt=sp)
            session = await agent.new()
            try:
                await session.prompt(user_prompt)
            except RuntimeError:
                pass  # Max turn iterations — tool was still called; check messages below
            tool_called, tool_name = _extract_tool_called(session)
            if tool_called:
                call_count += 1
            run_parts.append(f"run{run_idx}: tool={tool_name if tool_called else 'none'}")
            logging.debug("[%s] run%d tool_called=%s name=%s",
                          label, run_idx, tool_called, tool_name)
        rate = f"{call_count}/{REPEATS}"
        runs = "  ".join(run_parts)
        print(f"[{label}] system={sp_label}  user={up_label}  | {runs}  | call_rate={rate}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="1.3 tool call intent gradient (35 calls)")
    parser.add_argument("--config",
                        default=str(Path.home() / ".config/little_agent/config.yaml"))
    parser.add_argument("--loglevel", default="WARNING")
    args = parser.parse_args()
    logging.basicConfig(level=args.loglevel.upper())
    asyncio.run(_run(_load_config(args.config)))


if __name__ == "__main__":
    main()
