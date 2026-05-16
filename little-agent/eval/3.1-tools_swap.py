"""Tools evaluation: name-vs-description and capability-overlap preference tests."""

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

REPEATS = 3
HISTORY_TURNS = 5  # number of injected history turns for G5/G6


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


def _swap_pair(pair: dict[str, ToolSpec]) -> dict[str, ToolSpec]:
    """Return new pair dict with only names swapped; descs and args unchanged."""
    names = list(pair.keys())
    assert len(names) == 2
    a, b = names
    return {
        b: ToolSpec(b, pair[a].desc, pair[a].args),
        a: ToolSpec(a, pair[b].desc, pair[b].args),
    }


def _specs_for_group(
    pair: dict[str, ToolSpec], swap: bool
) -> list[ToolSpec]:
    active_pair = _swap_pair(pair) if swap else pair
    return list(active_pair.values()) + list(CONTEXT_TOOLS.values())


# ---------------------------------------------------------------------------
# Test T-A: 6 groups
# ---------------------------------------------------------------------------

@dataclass
class Group:
    label: str
    pair: dict[str, ToolSpec]
    prompt: str
    history_tool: str | None  # tool name to spam in injected history, or None


# "target" tool = the one that should handle file reading
# common pair: read; uncommon pair: glorb
GROUPS: list[Group] = [
    Group("G1 common   no-name   no-history", COMMON_PAIR,   "What does the file /etc/hosts contain?",                    None),
    Group("G2 common   with-name no-history", COMMON_PAIR,   "Use the read tool to show me the content of /etc/hosts.",   None),
    Group("G3 uncommon no-name   no-history", UNCOMMON_PAIR, "What does the file /etc/hosts contain?",                    None),
    Group("G4 uncommon with-name no-history", UNCOMMON_PAIR, "Use the glorb tool to show me the content of /etc/hosts.",  None),
    Group("G5 common   no-name   history",    COMMON_PAIR,   "What does the file /etc/hosts contain?",                    "bash"),
    Group("G6 uncommon no-name   history",    UNCOMMON_PAIR, "What does the file /etc/hosts contain?",                    "sneave"),
    Group("G7 common   with-name history",    COMMON_PAIR,   "Use the read tool to show me the content of /etc/hosts.",   "bash"),
    Group("G8 uncommon with-name history",    UNCOMMON_PAIR, "Use the glorb tool to show me the content of /etc/hosts.",  "sneave"),
]


def _classify(baseline_winner: str, swap_counters: Counter[str], pair: dict[str, ToolSpec]) -> tuple[int, int, int]:
    """Return (name_dominant, desc_dominant, other) counts from swapped phase."""
    # In swapped state: baseline_winner now carries the OTHER tool's description.
    # Calling baseline_winner again = name-dominant (ignoring description change).
    # Calling the other tool = desc-dominant (following description, not name).
    names = list(pair.keys())
    other_name = [n for n in names if n != baseline_winner][0] if baseline_winner in names else None
    name_dom = swap_counters.get(baseline_winner, 0)
    desc_dom = swap_counters.get(other_name, 0) if other_name else 0
    neither = REPEATS - name_dom - desc_dom
    return name_dom, desc_dom, neither


async def _run_ta(config: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    for group in GROUPS:
        print(f"\n  [{group.label}]", flush=True)

        for phase, swap in [("baseline", False), ("swapped", True)]:
            counters: Counter[str] = Counter()

            for rep in range(REPEATS):
                call_log: list[str] = []
                specs = _specs_for_group(group.pair, swap)
                tools = _build_tools(specs, call_log)
                agent = _build_agent(config, tools)
                session = await agent.new()

                if group.history_tool is not None:
                    _inject_history(session, group.history_tool)

                await session.prompt(group.prompt)
                called = _called_tools(session)
                first = called[0] if called else "(none)"
                counters[first] += 1
                print(f"    {phase} rep{rep+1}: {called}", flush=True)

            results.append({
                "group": group.label,
                "pair": group.pair,
                "phase": phase,
                "counters": dict(counters),
            })

    return results


def _print_ta(results: list[dict[str, Any]]) -> None:
    print("\n=== tools_swap: Name vs Description (8 Groups, 2³) ===\n")
    header = f"{'Group':<40} {'Phase':<10} {'Baseline winner':<18} {'name_dom':>9} {'desc_dom':>9} {'other':>6} {'stable':>7}"
    print(header)
    print("-" * len(header))

    for i in range(0, len(results), 2):
        base_r = results[i]
        swap_r = results[i + 1]
        pair = base_r["pair"]
        base_c: Counter[str] = Counter(base_r["counters"])
        swap_c: Counter[str] = Counter(swap_r["counters"])

        base_winner = base_c.most_common(1)[0][0] if base_c else "?"
        base_stable = "yes" if len(base_c) == 1 else "no"

        name_dom, desc_dom, other = _classify(base_winner, swap_c, pair)
        swap_stable = "yes" if len(swap_c) == 1 else "no"

        print(f"{base_r['group']:<40} baseline   {base_winner:<18} {'':>9} {'':>9} {'':>6} {base_stable:>7}  {dict(base_c)}")
        print(f"{'':40} swapped    {'':<18} {name_dom:>9} {desc_dom:>9} {other:>6} {swap_stable:>7}  {dict(swap_c)}")
        print()

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def _evaluate(config_path: str) -> None:
    config = _load_config(config_path)
    print("--- tools_swap: Name vs Description (8 groups) ---")
    ta_results = await _run_ta(config)
    _print_ta(ta_results)


def main() -> None:
    parser = argparse.ArgumentParser(description="tools_swap evaluation (8 groups × 6 calls = 48)")
    parser.add_argument("--config", default=str(Path.home() / ".config/little_agent/config.yaml"))
    parser.add_argument("--loglevel", default="WARNING")
    args = parser.parse_args()
    logging.basicConfig(level=args.loglevel.upper())
    asyncio.run(_evaluate(args.config))


if __name__ == "__main__":
    main()
