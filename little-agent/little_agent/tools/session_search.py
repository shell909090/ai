"""SessionSearchProvider: ToolProvider that searches JSONL session histories."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast

from little_agent._utils import read_jsonl_lines
from little_agent.types import AsyncToolFn, JSONValue, Session

from .protocol import ToolArgDef, ToolDef

logger = logging.getLogger(__name__)

_SEARCH_TOOLDEF = ToolDef(
    desc="Search this session's history (including turns evicted from active context) by keyword",
    args=[
        ToolArgDef(
            name="query",
            type="string",
            desc="Substring keyword; empty string returns latest N",
            required=True,
        ),
        ToolArgDef(name="limit", type="integer", desc="Maximum number of results to return"),
        ToolArgDef(
            name="kind",
            type="string",
            desc="Filter: turn, any, user_prompt, assistant, tool_result",
        ),
    ],
)


def _extract_text(record: dict[str, Any]) -> str:
    """Extract searchable text from a JSONL record."""
    node_kind = str(record.get("kind", ""))
    if node_kind == "user_prompt":
        prompt = record.get("prompt", "")
        if isinstance(prompt, list):
            return " ".join(
                str(block.get("text", "")) if isinstance(block, dict) else str(block)
                for block in prompt
            )
        return str(prompt)
    if node_kind == "assistant":
        text_parts: list[str] = []
        text = str(record.get("text", ""))
        if text:
            text_parts.append(text)
        tool_calls = record.get("tool_calls", {})
        if tool_calls:
            text_parts.append(json.dumps(tool_calls, ensure_ascii=False))
        return " ".join(text_parts)
    if node_kind == "tool_result":
        results = record.get("results", {})
        return json.dumps(results, ensure_ascii=False) if results else ""
    return ""


def _snippet(text: str, max_len: int = 500) -> str:
    """Truncate text to max_len characters."""
    return text[:max_len]


def _group_turns(
    records: list[dict[str, Any]],
) -> tuple[list[list[dict[str, Any]]], dict[str, str]]:
    """Group records into turns and build node_id → turn_id mapping."""
    turns: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for rec in records:
        if rec.get("kind") == "user_prompt":
            if current:
                turns.append(current)
            current = [rec]
        else:
            current.append(rec)
    if current:
        turns.append(current)

    node_to_turn_id: dict[str, str] = {}
    for turn in turns:
        if turn:
            tid = str(turn[0].get("id", ""))
            for node in turn:
                nid = str(node.get("id", ""))
                if nid:
                    node_to_turn_id[nid] = tid

    return turns, node_to_turn_id


def _search_turns(
    turns: list[list[dict[str, Any]]],
    q: str,
    limit: int,
) -> list[dict[str, JSONValue]]:
    """Return matching turns in reverse-time order."""
    results: list[dict[str, JSONValue]] = []
    for turn in reversed(turns):
        if len(results) >= limit or not turn:
            break
        turn_texts = [(rec, _extract_text(rec)) for rec in turn]
        if q and not any(q in text.lower() for _, text in turn_texts):
            continue
        turn_id = str(turn[0].get("id", ""))
        turn_created = str(turn[0].get("created_at", ""))
        nodes_out: list[JSONValue] = [
            {"kind": str(rec.get("kind", "")), "snippet": _snippet(text)}
            for rec, text in turn_texts
        ]
        results.append({"turn_id": turn_id, "created_at": turn_created, "nodes": nodes_out})
    return results


def _search_nodes(
    records: list[dict[str, Any]],
    node_to_turn_id: dict[str, str],
    q: str,
    kind: str,
    limit: int,
) -> list[dict[str, JSONValue]]:
    """Return matching nodes in reverse-time order."""
    results: list[dict[str, JSONValue]] = []
    for rec in reversed(records):
        if len(results) >= limit:
            break
        rec_kind = str(rec.get("kind", ""))
        if kind != "any" and rec_kind != kind:
            continue
        text = _extract_text(rec)
        if q and q not in text.lower():
            continue
        node_id = str(rec.get("id", ""))
        results.append(
            {
                "turn_id": node_to_turn_id.get(node_id, ""),
                "node_id": node_id,
                "kind": rec_kind,
                "created_at": str(rec.get("created_at", "")),
                "snippet": _snippet(text),
            }
        )
    return results


def _filter_records(
    records: list[dict[str, Any]],
    *,
    query: str,
    kind: str,
    limit: int,
) -> list[dict[str, JSONValue]]:
    """Filter records by kind and query, returning results in reverse-time order."""
    turns, node_to_turn_id = _group_turns(records)
    q = query.lower()
    if kind == "turn":
        return _search_turns(turns, q, limit)
    return _search_nodes(records, node_to_turn_id, q, kind, limit)


class SessionSearchProvider:
    """ToolProvider that searches JSONL session histories.

    Constructed with a resolve_path callable from SessionJSONLStore so that
    it can locate per-session JSONL files without importing the store module.
    """

    def __init__(self, resolve_path: Callable[[str], Path]) -> None:
        self._resolve_path = resolve_path

    async def _search(
        self,
        session_id: str,
        query: str = "",
        kind: str = "turn",
        limit: int = 5,
    ) -> JSONValue:
        """Search session history by keyword."""
        import asyncio

        path = self._resolve_path(session_id)
        if not path.exists():
            return []
        all_records = await asyncio.to_thread(read_jsonl_lines, path)
        # Filter to this session only (needed for fixed-filename multi-session files).
        records = [r for r in all_records if str(r.get("session_id", "")) == session_id]
        return cast(JSONValue, _filter_records(records, query=query, kind=kind, limit=limit))

    def __iter__(self) -> Iterator[tuple[str, ToolDef, AsyncToolFn]]:
        """Yield the search_session tool triple."""

        async def search_session_fn(args: dict[str, JSONValue], session: Session) -> JSONValue:
            query = str(args.get("query", ""))
            kind = str(args.get("kind", "turn"))
            limit_raw = args.get("limit", 5)
            limit = int(limit_raw) if isinstance(limit_raw, (int, float)) else 5
            return await self._search(session.id, query=query, kind=kind, limit=limit)

        yield ("search_session", _SEARCH_TOOLDEF, search_session_fn)
