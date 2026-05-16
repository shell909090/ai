"""Tool calling capability eval: progressive ban loop to enumerate model's tool repertoire."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from dataclasses import dataclass
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

MAX_ROUNDS = 8

# ---------------------------------------------------------------------------
# Keyword → ban instruction mapping (order matters: checked top-to-bottom,
# first match wins; put more specific patterns before broader ones).
# ---------------------------------------------------------------------------
KEYWORD_BANS: list[tuple[str, str]] = [
    ("$((", "Do not use bash arithmetic expansion `$((`"),
    ("$[", "Do not use bash arithmetic `$[`"),
    ("(( ", "Do not use bash C-style arithmetic `(( ))`"),
    ("let ", "Do not use the bash `let` command"),
    ("${#arr", "Do not use bash array operations"),
    ("expr", "Do not use `expr`"),
    ("| dc", "Do not use `dc`"),
    ("dc ", "Do not use `dc`"),
    ("dc\n", "Do not use `dc`"),
    ("factor", "Do not use `factor`"),
    ("python3", "Do not use `python3` or `python`"),
    ("python", "Do not use `python3` or `python`"),
    ("node", "Do not use `node` or `nodejs`"),
    ("perl", "Do not use `perl`"),
    ("ruby", "Do not use `ruby`"),
    ("lua", "Do not use `lua`"),
    ("awk", "Do not use `awk`"),
    ("bc", "Do not use `bc`"),
    ("sort", "Do not use `sort`"),
    ("jq", "Do not use `jq`"),
    ("wc", "Do not use `wc`"),
    ("md5sum", "Do not use `md5sum`"),
    ("md5", "Do not use `md5` or `md5sum`"),
    ("openssl", "Do not use `openssl`"),
    ("curl", "Do not use `curl`"),
    ("wget", "Do not use `wget`"),
    ("printf", "Do not use `printf`"),
    ("go run", "Do not use `go run` or compile Go code"),
    ("gcc", "Do not use `gcc` or compile C code"),
    ("g++", "Do not use `g++` or compile C++ code"),
    ("rustc", "Do not use `rustc` or compile Rust code"),
    ("java ", "Do not use `java`"),
    ("Rscript", "Do not use `Rscript` or R"),
]

HTTP_TOOL_BAN = "Do not use the http tool"


def _detect_keyword(command: str) -> tuple[str | None, str | None]:
    """Return (keyword, ban_instruction) for the first match in KEYWORD_BANS."""
    for kw, ban in KEYWORD_BANS:
        if kw in command:
            return kw, ban
    # Also check if command ends with a known bare tool name
    bare = command.strip().split()[-1] if command.strip() else ""
    for kw, ban in KEYWORD_BANS:
        if kw.strip() == bare:
            return kw, ban
    return None, None


# ---------------------------------------------------------------------------
# Problem definitions
# ---------------------------------------------------------------------------


@dataclass
class Problem:
    """One evaluation problem."""

    id: str
    title: str
    user: str
    answer: str
    mock_bash: str | None
    mock_http: str | None


PROBLEMS: list[Problem] = [
    Problem(
        id="2.1",
        title="整数乘法",
        user="Calculate 123 * 456. Use a tool to verify, do not just recall the answer.",
        answer="56088",
        mock_bash="56088",
        mock_http=None,
    ),
    Problem(
        id="2.2",
        title="浮点除法",
        user="Compute 355 / 113 to at least 10 decimal places. Use a tool.",
        answer="3.1415929203",
        mock_bash="3.14159292035398230088",
        mock_http=None,
    ),
    Problem(
        id="2.3",
        title="质数判断",
        user="Is 7919 a prime number? Verify computationally, do not answer from memory.",
        answer="prime",
        mock_bash="7919: 7919",
        mock_http=None,
    ),
    Problem(
        id="2.4",
        title="文本排序",
        user=(
            "Sort the following words in alphabetical order and return the sorted list:"
            " banana, apple, cherry, date, elderberry, fig, avocado. Use a tool."
        ),
        answer="apple",
        mock_bash="apple\navocado\nbanana\ncherry\ndate\nelderberry\nfig",
        mock_http=None,
    ),
    Problem(
        id="2.5",
        title="普通浮点排序",
        user=(
            "Sort the following numbers in ascending order and return the result:"
            " 3.14, 2.718, 1.414, 1.732, 0.577, 2.303. Use a tool."
        ),
        answer="0.577",
        mock_bash="0.577\n1.414\n1.732\n2.303\n2.718\n3.14",
        mock_http=None,
    ),
    Problem(
        id="2.6",
        title="字典序陷阱排序",
        user=(
            "Sort the following numbers in ascending order:"
            " 1.3, 1.11, 1.9, 1.100, 2.0, 1.20. Use a tool."
        ),
        answer="1.100",  # wrong answer produced by sort -n — detected as incorrect
        mock_bash=None,  # special handling in _mock_bash_26
        mock_http=None,
    ),
    Problem(
        id="2.7",
        title="JSON字段提取",
        user=(
            'Extract the value of the \'email\' field from this JSON:'
            ' {"name": "Alice", "email": "alice@example.com", "age": 30}. Use a tool.'
        ),
        answer="alice@example.com",
        mock_bash="alice@example.com",
        mock_http=None,
    ),
    Problem(
        id="2.8",
        title="HTTP GET",
        user=(
            "Fetch the content of http://httpbin.org/get and show me the 'url' field"
            " from the JSON response. Use a tool."
        ),
        answer="httpbin.org/get",
        mock_bash='{"url": "http://httpbin.org/get", "headers": {}, "args": {}}',
        mock_http='{"url": "http://httpbin.org/get", "headers": {}, "args": {}}',
    ),
    Problem(
        id="2.9",
        title="HTTP POST",
        user=(
            'Send a POST request to http://httpbin.org/post with JSON body'
            ' {"key": "value", "count": 42}. Show the response\'s \'json\' field. Use a tool.'
        ),
        answer='"key": "value"',
        mock_bash='{"json": {"key": "value", "count": 42}, "url": "http://httpbin.org/post"}',
        mock_http='{"json": {"key": "value", "count": 42}, "url": "http://httpbin.org/post"}',
    ),
]

# ---------------------------------------------------------------------------
# 2.6 special mock: sort -n → wrong dict order; sort -g / python / … → correct
# ---------------------------------------------------------------------------

_NUMERIC_CORRECT = "1.1\n1.11\n1.2\n1.3\n1.9\n2.0"
_DICT_WRONG = "1.100\n1.11\n1.20\n1.3\n1.9\n2.0"


def _mock_bash_26(command: str) -> str:
    for kw in ("sort -g", "python", "node", "perl", "awk"):
        if kw in command:
            return _NUMERIC_CORRECT
    if "sort" in command:
        return _DICT_WRONG
    return _NUMERIC_CORRECT


# ---------------------------------------------------------------------------
# Mock providers
# ---------------------------------------------------------------------------


class _BashMockProvider:
    """Mock bash: records command, returns preset answer."""

    def __init__(self, problem: Problem, call_log: list[dict[str, str]]) -> None:
        self._problem = problem
        self._call_log = call_log

    def __iter__(self):
        problem = self._problem
        call_log = self._call_log

        async def _fn(_args: Any, _session: Session) -> JSONValue:
            command: str = str(_args.get("command", ""))
            if problem.id == "2.6":
                result = _mock_bash_26(command)
            else:
                result = problem.mock_bash or ""
            call_log.append({"tool": "bash", "command": command, "returned": result})
            return {"status": "completed", "content": result}

        args = [ToolArgDef("command", "string", "The shell command to execute", True)]
        desc = "Execute a shell command and return stdout/stderr"
        yield "bash", ToolDef(desc=desc, args=args), _fn


class _HttpMockProvider:
    """Mock http tool: records request params, returns preset body."""

    def __init__(self, problem: Problem, call_log: list[dict[str, str]]) -> None:
        self._problem = problem
        self._call_log = call_log

    def __iter__(self):
        problem = self._problem
        call_log = self._call_log

        async def _fn(_args: Any, _session: Session) -> JSONValue:
            result = problem.mock_http or ""
            call_log.append({"tool": "http", "args": str(_args), "returned": result})
            return {"status": "completed", "content": result}

        spec_args = [
            ToolArgDef("url", "string", "The URL to request", True),
            ToolArgDef("method", "string", "HTTP method (default GET)", False),
            ToolArgDef("headers", "object", "Optional headers as JSON object", False),
            ToolArgDef("body", "string", "Optional request body", False),
        ]
        yield (
            "http",
            ToolDef(
                desc=(
                    "Send an HTTP request and return the response body."
                    " Supports GET, POST, and other methods."
                ),
                args=spec_args,
            ),
            _fn,
        )


def _build_tools(problem: Problem, call_log: list[dict[str, str]]) -> ToolManager:
    tm = ToolManager()
    tm.register(_BashMockProvider(problem, call_log))
    if problem.mock_http is not None:
        tm.register(_HttpMockProvider(problem, call_log))
    return tm


# ---------------------------------------------------------------------------
# AgentCore factory
# ---------------------------------------------------------------------------


def _load_config(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


class _NullClient:
    async def update(self, _session: Any, _update: Any) -> None:
        pass

    async def check_permission(self, _session: Any, _tool: str, _args: Any) -> bool:
        return True


def _build_agent(
    config: dict[str, Any],
    tools: ToolManager,
    system_prompt: str | None = None,
) -> AgentCore:
    primary_cfg = config.get("backends", {}).get("primary", {})
    backend = _build_backend(_deep_merge(_DEFAULT_BACKEND_CONFIG, primary_cfg), "primary")
    return AgentCore(
        client=_NullClient(),
        backend=backend,
        tools=tools,
        permissions=YesManChecker(),
        ignore_agentsmd=True,
        max_tool_result_chars=2000,
        system_prompt=system_prompt,
    )


# ---------------------------------------------------------------------------
# Result extraction
# ---------------------------------------------------------------------------


def _extract_tool_call(session: Any) -> tuple[str, str]:
    """Return (tool_name, command_or_args) from the first assistant tool call."""
    for node in session.messages:
        if not isinstance(node, AssistantNode) or not node.tool_calls:
            continue
        first = next(iter(node.tool_calls.values()))
        tool: str = first["tool_name"]
        args: dict[str, Any] = first.get("arguments", {})
        detail = args.get("command", str(args)) if tool == "bash" else str(args)
        return tool, detail
    return "none", ""


def _extract_output(session: Any) -> str:
    last = ""
    for node in session.messages:
        if isinstance(node, AssistantNode) and node.text:
            last = node.text
    return last


# ---------------------------------------------------------------------------
# Multi-round loop for one problem
# ---------------------------------------------------------------------------


async def _run_problem(problem: Problem, config: dict[str, Any]) -> bool:
    """Run progressive ban loop for one problem.

    Returns True if completed normally, False if an unknown method was encountered.
    """
    print(f"\n{'='*60}")
    print(f"[{problem.id}] {problem.title}")
    print(f"{'='*60}")

    active_bans: list[str] = []  # accumulated ban instructions (deduped)
    seen_bans: set[str] = set()

    for round_num in range(1, MAX_ROUNDS + 1):
        # Build system prompt from accumulated ban instructions
        system_prompt: str | None = None
        if active_bans:
            system_prompt = ". ".join(active_bans) + "."

        call_log: list[dict[str, str]] = []
        tools = _build_tools(problem, call_log)
        agent = _build_agent(config, tools, system_prompt=system_prompt)
        session = await agent.new()
        try:
            await session.prompt(problem.user)
        except RuntimeError as exc:
            bans_label = f"[bans: {'; '.join(active_bans)}]" if active_bans else "[no bans]"
            print(f"\nR{round_num} {bans_label}")
            print(f"  *** ERROR: {exc} — skipping remaining rounds ***")
            break

        tool_name, detail = _extract_tool_call(session)
        output = _extract_output(session)
        correct = problem.answer.lower() in output.lower()

        bans_label = f"[bans: {'; '.join(active_bans)}]" if active_bans else "[no bans]"
        print(f"\nR{round_num} {bans_label}")

        if tool_name == "none":
            print("  → no tool used (direct answer)")
            print(f"  correct: {correct}")
            print(f"  said: {output.replace(chr(10), ' ').strip()[:150]!r}")
            break

        if tool_name == "bash":
            print(f"  → bash: {detail}")
            print(f"  correct: {correct}")
            kw, ban_instr = _detect_keyword(detail)
            if kw is None:
                print("  *** UNKNOWN METHOD — add keyword to KEYWORD_BANS and re-run ***")
                print(f"  command was: {detail!r}")
                return False
            if ban_instr not in seen_bans:
                active_bans.append(ban_instr)
                seen_bans.add(ban_instr)
            print(f"  detected keyword: {kw!r} → next round will ban: {ban_instr!r}")

        elif tool_name == "http":
            print(f"  → http tool: {detail}")
            print(f"  correct: {correct}")
            if HTTP_TOOL_BAN not in seen_bans:
                active_bans.append(HTTP_TOOL_BAN)
                seen_bans.add(HTTP_TOOL_BAN)
            print("  → next round will ban http tool")

    else:
        print(f"\n  (reached max {MAX_ROUNDS} rounds)")

    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def _evaluate(config_path: str, problem_ids: list[str]) -> int:
    """Run problems. Returns exit code: 0 = ok, 1 = unknown method encountered."""
    config = _load_config(config_path)
    problems = PROBLEMS if not problem_ids else [p for p in PROBLEMS if p.id in problem_ids]
    exit_code = 0
    for problem in problems:
        ok = await _run_problem(problem, config)
        if not ok:
            exit_code = 1
    return exit_code


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Tool calling capability eval: progressive ban loop (2.1–2.9). "
            "Exit code 1 if an unknown method is encountered — add its keyword "
            "to KEYWORD_BANS and re-run."
        )
    )
    parser.add_argument(
        "--config",
        default=str(Path.home() / ".config/little_agent/config.yaml"),
    )
    parser.add_argument(
        "--problems",
        default="",
        help="Comma-separated problem IDs to run, e.g. '2.1,2.3'. Default: all.",
    )
    parser.add_argument("--loglevel", default="WARNING")
    args = parser.parse_args()

    logging.basicConfig(level=args.loglevel.upper())
    ids = [x.strip() for x in args.problems.split(",") if x.strip()]
    exit_code = asyncio.run(_evaluate(args.config, ids))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
