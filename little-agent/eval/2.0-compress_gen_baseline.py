"""Generate compress baseline by querying the primary backend.

Writes JSONL records to stdout; progress messages go to stderr.
Usage:
    uv run python eval/compress_gen_baseline.py > eval/compress_baseline.jsonl
    # or via Makefile: make eval/compress_baseline.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from little_agent._utils import _deep_merge
from little_agent.agent.compressor import _CompressorSession
from little_agent.backends.build import _DEFAULT_BACKEND_CONFIG, _build_backend
from little_agent.backends.protocol import BackendTurnResult

logger = logging.getLogger(__name__)

_DATASETS: list[dict[str, Any]] = [
    {
        "id": "les_mis",
        "title": "Les Misérables",
        "source_lang": "en",
        "keywords": [
            "Jean Valjean", "24601", "Bishop Myriel", "Javert",
            "Fantine", "Cosette", "Thénardiers", "Marius",
        ],
        "questions": [
            "Give me a detailed account of Jean Valjean's transformation from convict"
            " number 24601 to mayor of Montreuil-sur-Mer. What role did Bishop Myriel"
            " play in this change?",
            "Describe the relationship between Javert and Jean Valjean in Les Misérables."
            " How does their conflict embody the tension between law and mercy?"
            " How does Javert's story end?",
            "What is Fantine's story in Les Misérables? Describe her life, her"
            " relationship with Cosette, and what she sacrifices."
            " What does her fate represent thematically?",
            "Who are the Thénardiers in Les Misérables? Describe their character,"
            " their treatment of Cosette, and how they interact with Jean Valjean"
            " throughout the novel.",
            "How does the relationship between Cosette and Marius develop in"
            " Les Misérables? How does Jean Valjean respond to their love?"
            " How does the novel end for all three of them?",
        ],
    },
    {
        "id": "hong_lou_meng",
        "title": "红楼梦",
        "source_lang": "zh",
        "keywords": [
            "贾宝玉", "林黛玉", "薛宝钗", "神瑛侍者",
            "林如海", "贾母", "大观园", "元妃",
        ],
        "questions": [
            "请详细介绍红楼梦中贾宝玉的出身、性格和他在贾府中的地位。"
            "他衔玉而生有何象征？他与神瑛侍者的关系是什么？",
            "林黛玉的身世和性格如何？她与贾宝玉之间的感情经历了怎样的发展？"
            "林如海和贾母在她的命运中各自扮演什么角色？",
            "薛宝钗是怎样的人？请详细比较她与林黛玉在性格、处世方式上的不同。"
            "金玉良缘指的是什么，她最终的命运如何？",
            "大观园是如何建造的，有什么象征意义？它与元妃省亲有何关联？"
            "大观园中居住着哪些主要人物，各住何处？",
            "贾母在红楼梦中的权威体现在哪些方面？她对贾宝玉、林黛玉、薛宝钗各是什么态度？"
            "在宝玉的婚事上，她的立场与最终结果是什么？",
        ],
    },
]


def _load_config(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _build_primary(config: dict[str, Any]) -> Any:
    primary_cfg = config.get("backends", {}).get("primary", {})
    if not isinstance(primary_cfg, dict):
        raise ValueError("Config missing backends.primary")
    return _build_backend(_deep_merge(_DEFAULT_BACKEND_CONFIG, primary_cfg), "primary")


async def _ask(backend: Any, question: str) -> str:
    """Ask one question; return the assistant reply text."""
    session = _CompressorSession(question)
    result: BackendTurnResult | None = None
    async for item in backend.generate(session):
        if isinstance(item, BackendTurnResult):
            result = item
    if result is None:
        raise RuntimeError("Backend returned no result")
    return result.output_text


async def _generate(config_path: str) -> None:
    config = _load_config(config_path)
    backend = _build_primary(config)

    for dataset in _DATASETS:
        turns: list[dict[str, str]] = []
        print(f"[{dataset['id']}] {len(dataset['questions'])} questions", file=sys.stderr, flush=True)
        for i, question in enumerate(dataset["questions"]):
            print(f"  Q{i + 1}: {question[:70]}...", file=sys.stderr, flush=True)
            answer = await _ask(backend, question)
            turns.append({"user": question, "assistant": answer})
            print(f"       -> {len(answer)} chars", file=sys.stderr, flush=True)

        record = {
            "id": dataset["id"],
            "title": dataset["title"],
            "source_lang": dataset["source_lang"],
            "keywords": dataset["keywords"],
            "turns": turns,
        }
        print(json.dumps(record, ensure_ascii=False), flush=True)

    print(f"done: {len(_DATASETS)} datasets", file=sys.stderr, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate compress baseline conversations (JSONL to stdout)"
    )
    parser.add_argument(
        "--config",
        default=str(Path.home() / ".config/little_agent/config.yaml"),
    )
    parser.add_argument("--loglevel", default="WARNING")
    args = parser.parse_args()
    logging.basicConfig(level=args.loglevel.upper())
    asyncio.run(_generate(args.config))


if __name__ == "__main__":
    main()
