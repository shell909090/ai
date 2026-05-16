"""工具选择偏好：测试专用工具与 bash 在不同历史条件下的竞争结果。"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import uuid
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from little_agent._utils import _deep_merge
from little_agent.agent.agent import AgentCore
from little_agent.agent.nodes import AssistantNode, ToolResultNode, UserPromptNode
from little_agent.agent.permissions import YesManChecker
from little_agent.agent.tool_manager import ToolManager
from little_agent.backends.build import _DEFAULT_BACKEND_CONFIG, _build_backend
from little_agent.tools.protocol import ToolArgDef, ToolDef
from little_agent.types import JSONValue, Session

REPEATS = 5
HISTORY_TURNS = 5

# ---------------------------------------------------------------------------
# Tool spec registry
# ---------------------------------------------------------------------------

@dataclass
class ToolSpec:
    name: str
    desc: str
    args: list[ToolArgDef] = field(default_factory=list)


# Common names: model has pre-trained associations
COMMON_PAIR: dict[str, ToolSpec] = {
    "bash": ToolSpec(
        "bash",
        "Execute a shell command and return stdout/stderr",
        [ToolArgDef("command", "string", "The shell command to execute", True)],
    ),
    "read": ToolSpec(
        "read",
        "Read the contents of a file",
        [ToolArgDef("path", "string", "Absolute path to the file", True)],
    ),
}

# Uncommon names: invented words, model has no pre-trained associations
UNCOMMON_PAIR: dict[str, ToolSpec] = {
    "glorb": ToolSpec(
        "glorb",
        "Read the contents of a file",
        [ToolArgDef("path", "string", "Absolute path to the file", True)],
    ),
    "sneave": ToolSpec(
        "sneave",
        "Execute a shell command and return stdout/stderr",
        [ToolArgDef("command", "string", "The shell command to execute", True)],
    ),
}

# All other tools registered as neutral context
CONTEXT_TOOLS: dict[str, ToolSpec] = {
    "glob": ToolSpec(
        "glob",
        "Find files matching a glob pattern",
        [ToolArgDef("pattern", "string", "Glob pattern, e.g. **/*.py", True)],
    ),
    "grep": ToolSpec(
        "grep",
        "Search for a regex pattern within files",
        [
            ToolArgDef("pattern", "string", "Regex pattern to search for", True),
            ToolArgDef("path", "string", "Directory or file to search in", True),
        ],
    ),
    "write": ToolSpec(
        "write",
        "Write or overwrite a file with new content",
        [
            ToolArgDef("path", "string", "Path to the file", True),
            ToolArgDef("content", "string", "Content to write", True),
        ],
    ),
    "webfetch": ToolSpec(
        "webfetch",
        "Fetch and return the content of a URL",
        [ToolArgDef("url", "string", "The URL to fetch", True)],
    ),
    "task": ToolSpec(
        "task",
        "Run a sub-task prompt in a new agent session and return its output",
        [ToolArgDef("prompt", "string", "The sub-task prompt", True)],
    ),
}


# ---------------------------------------------------------------------------
# Mock ToolProvider
# ---------------------------------------------------------------------------

class MockProvider:
    """Single mock tool: records call, returns immediately without executing."""

    def __init__(self, spec: ToolSpec, call_log: list[str]) -> None:
        self._spec = spec
        self._call_log = call_log

    def __iter__(self):
        spec = self._spec
        call_log = self._call_log

        async def _fn(_args: Any, _session: Session) -> JSONValue:
            call_log.append(spec.name)
            return {"status": "completed", "content": f"mock result from {spec.name}"}

        yield spec.name, ToolDef(desc=spec.desc, args=spec.args), _fn


def _build_tools(specs: list[ToolSpec], call_log: list[str]) -> ToolManager:
    tm = ToolManager()
    for spec in specs:
        tm.register(MockProvider(spec, call_log))
    return tm


# ---------------------------------------------------------------------------
# AgentCore factory
# ---------------------------------------------------------------------------

def _load_config(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _build_agent(config: dict[str, Any], tools: ToolManager) -> AgentCore:
    primary_cfg = config.get("backends", {}).get("primary", {})
    backend = _build_backend(_deep_merge(_DEFAULT_BACKEND_CONFIG, primary_cfg), "primary")
    return AgentCore(
        client=_NullClient(),
        backend=backend,
        tools=tools,
        permissions=YesManChecker(),
        ignore_agentsmd=True,
        max_tool_result_chars=200,
    )


class _NullClient:
    async def update(self, _session: Any, _update: Any) -> None:
        pass

    async def check_permission(self, _session: Any, _tool: str, _args: Any) -> bool:
        return True


# ---------------------------------------------------------------------------
# History injection
# ---------------------------------------------------------------------------

def _inject_history(session: Any, tool_name: str, n_turns: int = HISTORY_TURNS) -> None:
    """Inject n turns of history where the assistant calls tool_name each time."""
    for i in range(n_turns):
        call_id = f"hist_call_{i}"
        user_node = UserPromptNode(
            id=str(uuid.uuid4()),
            prompt=f"Please handle task {i + 1}.",
        )
        assistant_node = AssistantNode(
            id=str(uuid.uuid4()),
            text=f"I'll use {tool_name} for this.",
            tool_calls={call_id: {"tool_name": tool_name, "arguments": {"command": f"echo task{i}"}}},
        )
        result_node = ToolResultNode(
            id=str(uuid.uuid4()),
            results={call_id: {"status": "completed", "content": f"task{i} done"}},
        )
        session.messages.extend([user_node, assistant_node, result_node])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _called_tools(session: Any) -> list[str]:
    """Return tool names from the FIRST assistant turn that made tool calls."""
    for node in session.messages:
        if isinstance(node, AssistantNode) and node.tool_calls:
            # skip injected history nodes (tool names match HISTORY pattern)
            if any(tc["tool_name"].startswith("hist") for tc in node.tool_calls.values()):
                continue
            return [tc["tool_name"] for tc in node.tool_calls.values()]
    return []


# ---------------------------------------------------------------------------
# 重叠功能偏好（4 场景 × 3 历史条件 × 5 次 = 60 调用）
# ---------------------------------------------------------------------------

@dataclass
class SelectCase:
    label: str
    tool_names: list[str]
    prompt: str
    specialized_tool: str  # the "right" tool for history bias testing


SELECT_CASES: list[SelectCase] = [
    SelectCase("读文件",   ["read", "bash"],        "Show me the content of /etc/hosts.",                         "read"),
    SelectCase("下载网页", ["webfetch", "bash"],     "What is on the page at http://example.com?",                "webfetch"),
    SelectCase("搜索文件", ["glob", "grep", "bash"], "Find all .py files that contain the word 'asyncio'.",       "grep"),
    SelectCase("写文件",   ["write", "bash"],        "Create a file named test.txt containing the text 'hello'.", "write"),
]

# (hist_label, hist_tool_key)  key: None=no history, "specialized"=case.specialized_tool, "bash"=bash
HISTORY_CONDITIONS: list[tuple[str, str | None]] = [
    ("无历史",    None),
    ("历史→专用", "specialized"),
    ("历史→bash", "bash"),
]

ALL_SPECS: dict[str, ToolSpec] = {**COMMON_PAIR, **CONTEXT_TOOLS}


async def _run_select(config: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    for case in SELECT_CASES:
        specs = [ALL_SPECS[n] for n in case.tool_names]
        for hist_label, hist_key in HISTORY_CONDITIONS:
            hist_tool: str | None
            if hist_key is None:
                hist_tool = None
            elif hist_key == "specialized":
                hist_tool = case.specialized_tool
            else:
                hist_tool = hist_key  # "bash"

            counters: Counter[str] = Counter()
            for rep in range(REPEATS):
                call_log: list[str] = []
                tools = _build_tools(specs, call_log)
                agent = _build_agent(config, tools)
                session = await agent.new()
                if hist_tool is not None:
                    _inject_history(session, hist_tool)
                await session.prompt(case.prompt)
                called = _called_tools(session)
                first = called[0] if called else "(none)"
                counters[first] += 1
                print(f"  {case.label} [{hist_label}] rep{rep+1}: {called}", flush=True)

            results.append({
                "case": case.label,
                "tools": case.tool_names,
                "hist": hist_label,
                "counters": dict(counters),
            })
        print(flush=True)

    return results


def _print_select(results: list[dict[str, Any]]) -> None:
    print("\n=== 重叠功能偏好 ===")
    print(f"  {'场景':<8} {'历史条件':<12} {'结果分布'}")
    print("  " + "-" * 50)
    for r in results:
        dist = "  ".join(f"{k}:{v}" for k, v in sorted(r["counters"].items(), key=lambda x: -x[1]))
        print(f"  {r['case']:<8} {r['hist']:<12} {dist}")



# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def _evaluate(config_path: str) -> None:
    config = _load_config(config_path)
    print("--- 重叠功能偏好 (4×3×5=60) ---")
    select_results = await _run_select(config)
    _print_select(select_results)


def main() -> None:
    parser = argparse.ArgumentParser(description="工具选择偏好评估 (60 次调用)")
    parser.add_argument("--config", default=str(Path.home() / ".config/little_agent/config.yaml"))
    parser.add_argument("--loglevel", default="WARNING")
    args = parser.parse_args()
    logging.basicConfig(level=args.loglevel.upper())
    asyncio.run(_evaluate(args.config))


if __name__ == "__main__":
    main()
