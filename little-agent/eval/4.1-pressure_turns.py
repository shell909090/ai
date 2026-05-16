"""Pressure test: turn count vs token count — find model stability threshold."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from collections.abc import AsyncIterator
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

TURN_TIMEOUT_S = 300
OUTPUT_TOKENS_ALARM = 20_000
MAX_TURNS = 999

NEUTRAL_MSGS = [
    "What is the capital of Japan?",
    "How does photosynthesis work?",
    "Who wrote Hamlet?",
    "What is the speed of light?",
    "Name three programming languages invented before 1980.",
    "What causes tides?",
    "What is the boiling point of water at sea level?",
    "Who painted the Mona Lisa?",
    "What is the largest planet in the solar system?",
    "How many bones are in the human body?",
]

# Mode B: each turn adds ~150 tokens of background context to stress token accumulation
_LONG_PREFIX = (
    "Here is some background context: "
    "The history of computing spans many decades, from mechanical calculators to modern "
    "quantum computers. Charles Babbage designed the Analytical Engine in the 19th century, "
    "considered a precursor to modern computers. Ada Lovelace wrote what is considered the "
    "first algorithm for such a machine. Alan Turing later formalized the concept of "
    "computation, and ENIAC became one of the first general-purpose electronic computers. "
    "Given that context, please answer: "
)


# ---------------------------------------------------------------------------
# Instrumented backend: captures per-call stats from BackendTurnResult
# ---------------------------------------------------------------------------

class _InstrumentedBackend:
    """Proxy backend that records stats from each BackendTurnResult."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.last: dict[str, Any] = {}

    @property
    def context_window(self) -> int:
        return self._inner.context_window

    async def generate(self, session: Any) -> AsyncIterator:
        async for item in self._inner.generate(session):
            if hasattr(item, "finish_reason") and hasattr(item, "output_text"):
                usage = getattr(item, "usage", None) or {}
                self.last = {
                    "finish_reason": item.finish_reason,
                    "input_tokens": usage.get("input_tokens"),
                    "output_tokens": usage.get("output_tokens"),
                    "text_len": len(item.output_text),
                }
            yield item


# ---------------------------------------------------------------------------
# Turn result
# ---------------------------------------------------------------------------

@dataclass
class TurnResult:
    """Stats for a single turn."""

    turn: int
    elapsed_s: float
    input_tokens: int | None
    output_tokens: int | None
    text_len: int
    status: str  # ok | timeout | runaway | error

    def failed(self) -> bool:
        return self.status != "ok"

    def __str__(self) -> str:  # noqa: D105
        it = self.input_tokens if self.input_tokens is not None else "?"
        ot = self.output_tokens if self.output_tokens is not None else "?"
        return (
            f"T{self.turn:03d}  in={it}  out={ot}"
            f"  elapsed={self.elapsed_s:.1f}s  text_len={self.text_len}"
            f"  [{self.status}]"
        )


def _classify(elapsed_s: float, output_tokens: int | None) -> str:
    if elapsed_s >= TURN_TIMEOUT_S:
        return "timeout"
    if output_tokens is not None and output_tokens >= OUTPUT_TOKENS_ALARM:
        return "runaway"
    return "ok"


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------

class _NullClient:
    async def update(self, _s: Any, _u: Any) -> None:
        pass

    async def check_permission(self, _s: Any, _t: str, _a: Any) -> bool:
        return True


def _load_config(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _build(config: dict[str, Any]) -> tuple[AgentCore, _InstrumentedBackend]:
    raw = _build_backend(
        _deep_merge(_DEFAULT_BACKEND_CONFIG, config.get("backends", {}).get("primary", {})),
        "primary",
    )
    backend = _InstrumentedBackend(raw)
    agent = AgentCore(
        client=_NullClient(),
        backend=backend,
        tools=ToolManager(),
        permissions=YesManChecker(),
        ignore_agentsmd=True,
    )
    return agent, backend


def _last_text(session: Any) -> str:
    last = ""
    for node in session.messages:
        if isinstance(node, AssistantNode) and node.text:
            last = node.text
    return last


def _make_msg(turn: int, long_mode: bool) -> str:
    base = NEUTRAL_MSGS[(turn - 1) % len(NEUTRAL_MSGS)]
    return _LONG_PREFIX + base if long_mode else base


# ---------------------------------------------------------------------------
# Single mode runner
# ---------------------------------------------------------------------------

async def _run_mode(config: dict[str, Any], long_mode: bool, max_turns: int) -> None:
    label = "B (long content)" if long_mode else "A (short questions)"
    print(f"\n{'='*60}")
    print(f"Mode {label} | timeout={TURN_TIMEOUT_S}s | alarm=output_tokens>={OUTPUT_TOKENS_ALARM}")
    print(f"{'='*60}")

    agent, backend = _build(config)
    session = await agent.new()
    results: list[TurnResult] = []

    for turn in range(1, max_turns + 1):
        msg = _make_msg(turn, long_mode)
        t0 = time.monotonic()
        try:
            await asyncio.wait_for(session.prompt(msg), timeout=float(TURN_TIMEOUT_S))
        except TimeoutError:
            elapsed = time.monotonic() - t0
            r = TurnResult(
                turn=turn, elapsed_s=elapsed,
                input_tokens=None, output_tokens=None,
                text_len=0, status="timeout",
            )
            results.append(r)
            print(r)
            print(f"\n*** TIMEOUT at T{turn} after {elapsed:.0f}s — stopping ***")
            break
        except Exception as exc:
            elapsed = time.monotonic() - t0
            r = TurnResult(
                turn=turn, elapsed_s=elapsed,
                input_tokens=backend.last.get("input_tokens"),
                output_tokens=backend.last.get("output_tokens"),
                text_len=0, status="error",
            )
            results.append(r)
            print(f"{r}  error={exc!r:.80}")
            print(f"\n*** ERROR at T{turn} — stopping ***")
            break

        elapsed = time.monotonic() - t0
        out_tok = backend.last.get("output_tokens")
        in_tok = backend.last.get("input_tokens")
        text = _last_text(session)
        status = _classify(elapsed, out_tok)

        r = TurnResult(
            turn=turn, elapsed_s=elapsed,
            input_tokens=in_tok, output_tokens=out_tok,
            text_len=len(text), status=status,
        )
        results.append(r)
        print(r)

        if r.failed():
            print(f"\n*** FAILURE at T{turn}: {status} — stopping ***")
            break

    # Summary
    ok = [r for r in results if not r.failed()]
    failed = [r for r in results if r.failed()]
    print(f"\n--- Summary (Mode {label}) ---")
    print(f"Completed turns: {len(ok)}")
    if failed:
        f = failed[0]
        print(f"First failure:   T{f.turn} ({f.status})")
        print(f"  input_tokens:  {f.input_tokens}")
        print(f"  output_tokens: {f.output_tokens}")
        print(f"  elapsed:       {f.elapsed_s:.1f}s")
    else:
        last = results[-1] if results else None
        if last:
            print(f"No failure in {len(results)} turns")
            print(f"  Last input_tokens: {last.input_tokens}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def _main(args: argparse.Namespace) -> None:
    config = _load_config(args.config)
    for run_idx in range(1, args.runs + 1):
        if args.runs > 1:
            print(f"\n### Run {run_idx}/{args.runs} ###")
        if args.mode in ("A", "both"):
            await _run_mode(config, long_mode=False, max_turns=args.max_turns)
        if args.mode in ("B", "both"):
            await _run_mode(config, long_mode=True, max_turns=args.max_turns)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pressure test: turn count vs token count stability threshold"
    )
    parser.add_argument(
        "--config", default=str(Path.home() / ".config/little_agent/config.yaml")
    )
    parser.add_argument(
        "--mode", choices=["A", "B", "both"], default="A",
        help="A=short questions, B=long content per turn, both=run sequentially",
    )
    parser.add_argument("--max-turns", type=int, default=MAX_TURNS)
    parser.add_argument("--runs", type=int, default=3, help="Number of independent runs")
    parser.add_argument("--loglevel", default="WARNING")
    args = parser.parse_args()
    logging.basicConfig(level=args.loglevel.upper())
    asyncio.run(_main(args))


if __name__ == "__main__":
    main()
