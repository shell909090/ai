"""Pressure test: data feeding — feed novel paragraphs, ask about previous paragraph details."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
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
MAX_TURNS = 999  # run until crash

# ---------------------------------------------------------------------------
# Corpus: synthetic paragraphs with specific details + Q&A
# Each entry: (paragraph_text, question, answer_keywords)
# Paragraphs are ~150-200 tokens each to accumulate context pressure
# ---------------------------------------------------------------------------

def _load_corpus(path: str | None = None) -> list[tuple[str, str, list[str]]]:
    """Load corpus from JSONL file, falling back to embedded samples."""
    import json as _json
    default_path = Path(__file__).parent / "pressure_corpus.jsonl"
    fpath = Path(path) if path else default_path
    if not fpath.exists():
        raise FileNotFoundError(f"Corpus file not found: {fpath}")
    entries = []
    with open(fpath, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = _json.loads(line)
            text = obj.get("text", obj.get("paragraph", ""))
            entries.append((text, obj["question"], obj["keywords"]))
    return entries


CORPUS = _load_corpus()


# ---------------------------------------------------------------------------
# Backend (no instrumentation needed — we just watch context grow)
# ---------------------------------------------------------------------------


@dataclass
class TurnResult:
    """Stats for a single turn."""

    turn: int
    kind: str  # "feed" | "ask"
    elapsed_s: float
    input_tokens: int | None
    output_tokens: int | None
    correct: bool | None  # None for feed turns
    status: str  # ok | timeout | runaway | incoherent | error

    def failed(self) -> bool:
        return self.status in ("timeout", "runaway", "error")

    def __str__(self) -> str:  # noqa: D105
        it = self.input_tokens if self.input_tokens is not None else "?"
        ot = self.output_tokens if self.output_tokens is not None else "?"
        verdict = ""
        if self.kind == "ask":
            verdict = f"  correct={self.correct}"
        return (
            f"T{self.turn:03d}[{self.kind:4}]  in={it}  out={ot}"
            f"  elapsed={self.elapsed_s:.1f}s{verdict}"
            f"  [{self.status}]"
        )


def _load_config(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


class _NullClient:
    async def update(self, _s: Any, _u: Any) -> None:
        pass

    async def check_permission(self, _s: Any, _t: str, _a: Any) -> bool:
        return True


def _build_agent(config: dict[str, Any]) -> tuple[AgentCore, Any]:
    from collections.abc import AsyncIterator

    class _Backend:
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
                        "input_tokens": usage.get("input_tokens"),
                        "output_tokens": usage.get("output_tokens"),
                    }
                yield item

    raw = _build_backend(
        _deep_merge(_DEFAULT_BACKEND_CONFIG, config.get("backends", {}).get("primary", {})),
        "primary",
    )
    backend = _Backend(raw)
    agent = AgentCore(
        client=_NullClient(), backend=backend, tools=ToolManager(),
        permissions=YesManChecker(), ignore_agentsmd=True,
    )
    return agent, backend


def _extract_output(session: Any) -> str:
    last = ""
    for node in session.messages:
        if isinstance(node, AssistantNode) and node.text:
            last = node.text
    return last


def _classify(elapsed_s: float, output_tokens: int | None, correct: bool | None) -> str:
    if elapsed_s >= TURN_TIMEOUT_S:
        return "timeout"
    if output_tokens is not None and output_tokens >= OUTPUT_TOKENS_ALARM:
        return "runaway"
    if correct is False:
        return "incoherent"
    return "ok"


async def _run_once(config: dict[str, Any], run_idx: int, runs: int) -> None:
    label = f"Run {run_idx}/{runs}"
    print(f"\n{'='*60}")
    print(f"4.2 Data Pressure | {label} | timeout={TURN_TIMEOUT_S}s")
    print(f"{'='*60}")

    agent, backend = _build_agent(config)
    session = await agent.new()
    results: list[TurnResult] = []
    corpus_idx = 0

    turn = 0
    while corpus_idx < len(CORPUS):
        corpus_entry = CORPUS[corpus_idx]
        para, question, keywords = corpus_entry[0], corpus_entry[1], corpus_entry[2]

        # Feed turn
        turn += 1
        feed_msg = f"请帮我总结一下这段文字的要点（保留关键事实、数字和人名）：\n\n{para}"
        t0 = time.monotonic()
        try:
            await asyncio.wait_for(session.prompt(feed_msg), timeout=float(TURN_TIMEOUT_S))
        except TimeoutError:
            elapsed = time.monotonic() - t0
            r = TurnResult(turn=turn, kind="feed", elapsed_s=elapsed,
                           input_tokens=None, output_tokens=None,
                           correct=None, status="timeout")
            results.append(r)
            print(r)
            print(f"\n*** TIMEOUT at T{turn} (feed) — stopping ***")
            break
        except Exception as exc:
            elapsed = time.monotonic() - t0
            r = TurnResult(turn=turn, kind="feed", elapsed_s=elapsed,
                           input_tokens=backend.last.get("input_tokens"),
                           output_tokens=backend.last.get("output_tokens"),
                           correct=None, status="error")
            results.append(r)
            print(f"{r}  err={exc!r:.60}")
            break
        elapsed = time.monotonic() - t0
        r = TurnResult(turn=turn, kind="feed",
                       elapsed_s=elapsed,
                       input_tokens=backend.last.get("input_tokens"),
                       output_tokens=backend.last.get("output_tokens"),
                       correct=None,
                       status=_classify(elapsed, backend.last.get("output_tokens"), None))
        results.append(r)
        print(r)
        if r.failed():
            print(f"\n*** FAILURE at T{turn} (feed): {r.status} ***")
            break

        # Ask turn
        turn += 1
        t0 = time.monotonic()
        try:
            await asyncio.wait_for(session.prompt(question), timeout=float(TURN_TIMEOUT_S))
        except TimeoutError:
            elapsed = time.monotonic() - t0
            r = TurnResult(turn=turn, kind="ask", elapsed_s=elapsed,
                           input_tokens=None, output_tokens=None,
                           correct=None, status="timeout")
            results.append(r)
            print(r)
            print(f"\n*** TIMEOUT at T{turn} (ask) — stopping ***")
            break
        except Exception as exc:
            elapsed = time.monotonic() - t0
            r = TurnResult(turn=turn, kind="ask", elapsed_s=elapsed,
                           input_tokens=backend.last.get("input_tokens"),
                           output_tokens=backend.last.get("output_tokens"),
                           correct=None, status="error")
            results.append(r)
            print(f"{r}  err={exc!r:.60}")
            break
        elapsed = time.monotonic() - t0
        output = _extract_output(session)
        correct = any(kw.lower() in output.lower() for kw in keywords)
        out_tok = backend.last.get("output_tokens")
        status = _classify(elapsed, out_tok, correct)
        r = TurnResult(turn=turn, kind="ask",
                       elapsed_s=elapsed,
                       input_tokens=backend.last.get("input_tokens"),
                       output_tokens=out_tok,
                       correct=correct, status=status)
        results.append(r)
        print(r)
        if r.failed():
            print(f"\n*** FAILURE at T{turn} (ask): {r.status} ***")
            break

        corpus_idx += 1

    # Summary
    ask_results = [r for r in results if r.kind == "ask"]
    correct_count = sum(1 for r in ask_results if r.correct)
    failed = [r for r in results if r.failed()]
    last_in = results[-1].input_tokens if results else None
    print(f"\n--- Summary ({label}) ---")
    print(f"Turns completed: {len(results)}  Ask turns: {len(ask_results)}")
    print(f"Correct answers: {correct_count}/{len(ask_results)}")
    print(f"Last input_tokens: {last_in}")
    if failed:
        f = failed[0]
        print(f"First failure: T{f.turn} ({f.status})")
        print(f"  input_tokens: {f.input_tokens}")
    else:
        print("No failure (corpus exhausted normally)")


async def _main(args: argparse.Namespace) -> None:
    config = _load_config(args.config)
    for run_idx in range(1, args.runs + 1):
        await _run_once(config, run_idx, args.runs)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="4.2 data pressure: feed paragraphs, ask details, find recall failure"
    )
    parser.add_argument("--config",
                        default=str(Path.home() / ".config/little_agent/config.yaml"))
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--corpus", default=None, help="Path to corpus JSONL file")
    parser.add_argument("--loglevel", default="WARNING")
    args = parser.parse_args()
    logging.basicConfig(level=args.loglevel.upper())
    if args.corpus:
        global CORPUS
        CORPUS = _load_corpus(args.corpus)
    asyncio.run(_main(args))


if __name__ == "__main__":
    main()
