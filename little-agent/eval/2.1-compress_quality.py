"""Compress evaluation: 9 instruction variants × 2 datasets × 3 repeats = 54 calls."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from little_agent._utils import _deep_merge
from little_agent.agent.compressor import _CompressorSession
from little_agent.backends.build import _DEFAULT_BACKEND_CONFIG, _build_backend
from little_agent.backends.protocol import BackendTurnResult

BASELINE_FILE = Path(__file__).parent / "compress_baseline.jsonl"
CSV_FILE = Path(__file__).parent / "compress_results.csv"
REPEATS = 3

COMPRESS_PROMPTS: dict[str, list[str]] = {
    "en": [
        (
            "Please summarize the following conversation, preserving all important facts,"
            " character names, key events, and significant details."
            " Be concise but complete:\n\n{history}"
        ),
        (
            "Provide a comprehensive summary of the conversation below."
            " Keep all key character names, plot events, and important details."
            " Aim for brevity without omitting essentials:\n\n{history}"
        ),
        (
            "Please summarize the following conversation IN ENGLISH, preserving all important"
            " facts, character names, key events, and significant details."
            " Be concise but complete:\n\n{history}"
        ),
    ],
    "zh": [
        "请总结以下对话，保留所有重要事实、人物姓名、关键事件和重要细节，要求简洁但完整：\n\n{history}",
        "请对以下对话进行概括，保留关键人物、重要情节和核心细节，力求简明扼要：\n\n{history}",
        "请用中文总结以下对话，保留所有重要事实、人物姓名、关键事件和重要细节，要求简洁但完整：\n\n{history}",
    ],
    "ja": [
        (
            "以下の会話を要約してください。重要な事実、人物名、重要な出来事、"
            "注目すべき詳細をすべて保持してください。簡潔かつ完全に：\n\n{history}"
        ),
        (
            "以下の会話の主要な内容を簡潔にまとめてください。登場人物名、重要な出来事、"
            "核心的な詳細を漏らさず含めてください：\n\n{history}"
        ),
        (
            "以下の会話を日本語で要約してください。重要な事実、人物名、重要な出来事、"
            "注目すべき詳細をすべて日本語で保持してください。簡潔かつ完全に：\n\n{history}"
        ),
    ],
}

LANGS = list(COMPRESS_PROMPTS.keys())


def _load_config(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _build_primary(config: dict[str, Any]) -> Any:
    primary_cfg = config.get("backends", {}).get("primary", {})
    if not isinstance(primary_cfg, dict):
        raise ValueError("Config missing backends.primary")
    return _build_backend(_deep_merge(_DEFAULT_BACKEND_CONFIG, primary_cfg), "primary")


def _format_history(turns: list[dict[str, str]]) -> str:
    parts: list[str] = []
    for t in turns:
        parts.append(f"User: {t['user']}")
        parts.append(f"Assistant: {t['assistant']}")
    return "\n\n".join(parts)


def _detect_lang(text: str) -> str:
    """Detect language using chardet; returns 'en', 'zh', or 'ja'."""
    import chardet
    lang = (chardet.detect(text.encode("utf-8")).get("language") or "").lower()
    if lang == "ja":
        return "ja"
    if lang == "zh":
        return "zh"
    return "en"


def _keyword_hits(text: str, keywords: list[str]) -> int:
    lower = text.lower()
    return sum(1 for kw in keywords if kw.lower() in lower)


async def _run_once(backend: Any, history: str, prompt_template: str) -> dict[str, Any]:
    prompt = prompt_template.format(history=history)
    session = _CompressorSession(prompt)
    result: BackendTurnResult | None = None
    async for item in backend.generate(session):
        if isinstance(item, BackendTurnResult):
            result = item
    if result is None:
        raise RuntimeError("Backend returned no result")
    usage = result.usage or {}
    return {
        "output_text": result.output_text,
        "finish_reason": result.finish_reason,
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
    }


async def _run_config(
    backend: Any,
    history: str,
    input_chars: int,
    keywords: list[str],
    lang: str,
    variant: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run one config REPEATS times concurrently.

    Returns (individual_rows, aggregated_row).
    """
    template = COMPRESS_PROMPTS[lang][variant]
    raw = await asyncio.gather(*[_run_once(backend, history, template) for _ in range(REPEATS)])

    individual: list[dict[str, Any]] = []
    ratios: list[float] = []
    lang_counts: Counter[str] = Counter()
    kw_passes = 0
    pass_count = 0

    for rep_idx, r in enumerate(raw):
        text: str = r["output_text"]
        out_chars = len(text)
        in_tok = r["input_tokens"] if r["input_tokens"] is not None else input_chars // 4
        out_tok = r["output_tokens"] if r["output_tokens"] is not None else out_chars // 4
        ratio = out_tok / max(in_tok, 1)
        ratios.append(ratio)
        hits = _keyword_hits(text, keywords)
        kw_ok = hits >= len(keywords) // 2
        out_lang = _detect_lang(text)
        lang_counts[out_lang] += 1
        if kw_ok:
            kw_passes += 1
        ok = r["finish_reason"] == "completed" and bool(text.strip()) and kw_ok
        if ok:
            pass_count += 1

        individual.append(
            {
                "lang": lang,
                "variant": f"p{variant + 1}",
                "rep": rep_idx + 1,
                "in_tok": in_tok,
                "out_tok": out_tok,
                "ratio": round(ratio, 4),
                "kw_hits": hits,
                "kw_total": len(keywords),
                "output_lang": out_lang,
                "passed": ok,
            }
        )

    lang_dist = " ".join(f"{l}:{n}" for l, n in sorted(lang_counts.items()))
    avg_ratio = sum(ratios) / len(ratios)

    agg = {
        "lang": lang,
        "variant": f"p{variant + 1}",
        "in_tok": individual[0]["in_tok"],
        "ratios": ratios,
        "avg_ratio": avg_ratio,
        "kw_pass": f"{kw_passes}/{REPEATS}",
        "lang_dist": lang_dist,
        "pass": f"{pass_count}/{REPEATS}",
        "all_pass": pass_count == REPEATS,
    }
    return individual, agg


def _print_table(dataset_id: str, rows: list[dict[str, Any]]) -> None:
    print(f"\n{'=' * 80}")
    print(f"  Dataset: {dataset_id}")
    print(f"{'=' * 80}")
    hdr = f"{'lang':4} {'var':3} {'in_tok':>7}  {'r1':>6} {'r2':>6} {'r3':>6}  {'avg':>6}  {'kw':>5}  {'lang_dist':>14}  {'pass':>6}"
    print(hdr)
    print("-" * 80)
    for r in rows:
        r1, r2, r3 = r["ratios"]
        print(
            f"{r['lang']:4} {r['variant']:3} {r['in_tok']:>7}  "
            f"{r1:>6.3f} {r2:>6.3f} {r3:>6.3f}  {r['avg_ratio']:>6.3f}  "
            f"{r['kw_pass']:>5}  {r['lang_dist']:>14}  {r['pass']:>6}"
        )
    all_pass = sum(1 for r in rows if r["all_pass"])
    print("-" * 80)
    print(f"  Configs fully passed: {all_pass}/{len(rows)}")


def _write_csv(all_individual: list[tuple[str, dict[str, Any]]]) -> None:
    """Write per-repetition raw data to CSV."""
    fields = ["dataset", "lang", "variant", "rep", "in_tok", "out_tok", "ratio",
              "kw_hits", "kw_total", "output_lang", "passed"]
    with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for dataset_id, row in all_individual:
            writer.writerow({"dataset": dataset_id, **row})
    print(f"\nRaw data -> {CSV_FILE}")


def _build_md_table(
    all_agg: dict[str, dict[tuple[str, str], dict[str, Any]]],
    dataset_ids: list[str],
) -> str:
    """Build markdown table: 9 rows × (3 ratio cols + kw + lang) per dataset."""
    # header
    ds_headers = " | ".join(
        f"{d} r1 | {d} r2 | {d} r3 | {d} kw | {d} lang" for d in dataset_ids
    )
    header = f"| 指令 | {ds_headers} |"
    sep_parts = ["---"] + ["---", "---", "---", "---", "---"] * len(dataset_ids)
    sep = "| " + " | ".join(sep_parts) + " |"

    lines = [header, sep]
    for lang in LANGS:
        for vi in range(3):
            variant = f"p{vi + 1}"
            label = f"{lang}-{variant}"
            cells = [label]
            for ds in dataset_ids:
                r = all_agg[ds][(lang, variant)]
                r1, r2, r3 = r["ratios"]
                cells += [
                    f"{r1:.3f}",
                    f"{r2:.3f}",
                    f"{r3:.3f}",
                    r["kw_pass"],
                    r["lang_dist"],
                ]
            lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


async def _evaluate(config_path: str, show_text: bool) -> bool:
    config = _load_config(config_path)
    backend = _build_primary(config)

    all_individual: list[tuple[str, dict[str, Any]]] = []
    all_agg: dict[str, dict[tuple[str, str], dict[str, Any]]] = {}
    dataset_ids: list[str] = []
    all_pass = True

    with open(BASELINE_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            dataset: dict[str, Any] = json.loads(line)
            ds_id: str = dataset["id"]
            dataset_ids.append(ds_id)
            history = _format_history(dataset["turns"])
            input_chars = len(history)
            keywords: list[str] = dataset["keywords"]

            agg_map: dict[tuple[str, str], dict[str, Any]] = {}
            table_rows: list[dict[str, Any]] = []

            for lang in LANGS:
                for variant in range(3):
                    label = f"{ds_id} {lang}-p{variant + 1}"
                    print(f"  {label} ({REPEATS}×) ...", end=" ", flush=True)
                    individual, agg = await _run_config(
                        backend, history, input_chars, keywords, lang, variant
                    )
                    for row in individual:
                        all_individual.append((ds_id, row))
                    agg_map[(lang, f"p{variant + 1}")] = agg
                    table_rows.append(agg)
                    r1, r2, r3 = agg["ratios"]
                    print(
                        f"ratios={r1:.3f}/{r2:.3f}/{r3:.3f} "
                        f"kw={agg['kw_pass']} {agg['lang_dist']}",
                        flush=True,
                    )
                    if not agg["all_pass"]:
                        all_pass = False

            all_agg[ds_id] = agg_map
            _print_table(ds_id, table_rows)

            if show_text:
                for lang in LANGS:
                    for vi in range(3):
                        template = COMPRESS_PROMPTS[lang][vi].format(history=history)
                        session = _CompressorSession(template)
                        result: BackendTurnResult | None = None
                        async for item in backend.generate(session):
                            if isinstance(item, BackendTurnResult):
                                result = item
                        if result:
                            print(f"\n=== {ds_id} / {lang}-p{vi + 1} ===")
                            print(result.output_text)

    _write_csv(all_individual)

    md_table = _build_md_table(all_agg, dataset_ids)
    print(f"\n{'=' * 80}")
    print("Markdown table (for compress.md):")
    print(f"{'=' * 80}")
    print(md_table)

    print(f"\nOverall: {'ALL PASSED' if all_pass else 'SOME FAILED'}")
    return all_pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Compress evaluation (54 calls)")
    parser.add_argument("--config", default=str(Path.home() / ".config/little_agent/config.yaml"))
    parser.add_argument("--loglevel", default="WARNING")
    parser.add_argument("--show-text", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=args.loglevel.upper())

    ok = asyncio.run(_evaluate(args.config, args.show_text))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
