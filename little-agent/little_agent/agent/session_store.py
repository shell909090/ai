"""SessionJSONLStore: Hook + ToolProvider that persists session nodes to JSONL files."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from little_agent.tools.protocol import AsyncToolFn, ToolArgDef, ToolDef
from little_agent.types import JSONValue

from .hooks import Hook

if TYPE_CHECKING:
    from little_agent.types import Session

logger = logging.getLogger(__name__)

_MAX_LOCKS: int = 1024

_SEARCH_TOOLDEF = ToolDef(
    desc=("Search this session's history (including turns evicted from active context) by keyword"),
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
            desc="Filter: turn, any, user_prompt, tool_call, tool_result, assistant_response",
        ),
    ],
)


class SessionJSONLStore(Hook):
    """Appends session nodes to per-session JSONL files and provides search_session tool."""

    def __init__(
        self,
        sessions_dir: str,
        filename_template: str = "{session_id}_session.jsonl",
    ) -> None:
        self._sessions_dir = Path(sessions_dir).expanduser()
        self._filename_template = filename_template
        self._last_tail_ids: dict[str, str] = {}  # evicted at _MAX_LOCKS cap
        self._locks: dict[str, asyncio.Lock] = {}
        self._init_locks: dict[str, asyncio.Lock] = {}
        self._rebuilt: set[str] = set()

        # For fixed filenames (no {session_id}), rebuild last_tail_ids at init time.
        # Called synchronously here because no event loop exists at startup.
        if "{session_id}" not in filename_template:
            path = self.resolve_path("")
            if path.exists():
                self._scan_file(path)
            self._rebuilt.add(str(path))

    def resolve_path(self, session_id: str) -> Path:
        """Return the JSONL file path for a session_id."""
        filename = self._filename_template.format(session_id=session_id)
        return self._sessions_dir / filename

    def _set_last_tail_id(self, session_id: str, node_id: str) -> None:
        """Record last tail id; evict oldest entry when cap is reached."""
        if session_id not in self._last_tail_ids and len(self._last_tail_ids) >= _MAX_LOCKS:
            self._last_tail_ids.pop(next(iter(self._last_tail_ids)))
        self._last_tail_ids[session_id] = node_id

    def _get_lock(self, path: Path) -> asyncio.Lock:
        """Return (creating if needed) the per-file write lock; evict oldest if at cap."""
        key = str(path)
        if key not in self._locks:
            if len(self._locks) >= _MAX_LOCKS:
                self._locks.pop(next(iter(self._locks)))
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    def _get_init_lock(self, path: Path) -> asyncio.Lock:
        """Return (creating if needed) the per-path init lock; evict oldest if at cap."""
        key = str(path)
        if key not in self._init_locks:
            if len(self._init_locks) >= _MAX_LOCKS:
                self._init_locks.pop(next(iter(self._init_locks)))
            self._init_locks[key] = asyncio.Lock()
        return self._init_locks[key]

    def _scan_file(self, path: Path) -> None:
        """Scan existing JSONL file and restore last_tail_ids from it."""
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        sid = record.get("session_id")
                        node_id = record.get("id")
                        if isinstance(sid, str) and isinstance(node_id, str):
                            self._set_last_tail_id(sid, node_id)
                    except json.JSONDecodeError:
                        pass
        except OSError:
            logger.exception("Failed to scan SessionJSONLStore file %s", path)

    def _sync_append(self, path: Path, nodes: list[Any], session_id: str) -> None:
        """Append serialised nodes to path; called via asyncio.to_thread inside the lock."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            for n in nodes:
                record: dict[str, Any] = {"session_id": session_id, **n.to_dict()}
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    async def on_turn_end(self, session: "Session") -> None:
        """Append new nodes from session.tail back to the last logged node."""
        from little_agent.agent.nodes import SummaryNode

        session_id: str = session.id
        path = self.resolve_path(session_id)
        lock = self._get_lock(path)

        # Lazy rebuild: use per-path init lock + double-check to prevent concurrent
        # sessions from skipping the scan before it completes.
        path_key = str(path)
        if path_key not in self._rebuilt:
            init_lock = self._get_init_lock(path)
            async with init_lock:
                if path_key not in self._rebuilt:  # double-check inside lock
                    if path.exists():
                        await asyncio.to_thread(self._scan_file, path)
                    self._rebuilt.add(path_key)  # mark only after scan completes

        stop_id = self._last_tail_ids.get(session_id)

        # Walk from tail backwards, collecting nodes until stop_id; skip SummaryNode.
        nodes: list[Any] = []
        node: Any = session.tail
        while node is not None:
            if node.id == stop_id:
                break
            if not isinstance(node, SummaryNode):
                nodes.append(node)
            node = node.prev

        if not nodes:
            return

        nodes.reverse()  # write oldest-first

        async with lock:
            await asyncio.to_thread(self._sync_append, path, nodes, session_id)

        assert session.tail is not None
        tail_id = getattr(session.tail, "id", None)
        if isinstance(tail_id, str):
            self._set_last_tail_id(session_id, tail_id)

    async def load_history(self, session_id: str) -> list[dict[str, JSONValue]]:
        """Read JSONL file for session_id and return list of records without session_id key."""
        path = self.resolve_path(session_id)
        if not path.exists():
            return []
        return await asyncio.to_thread(self._sync_read_history, path)

    async def delete_session(self, session_id: str) -> None:
        """Delete JSONL file for session_id and clean up internal state."""
        path = self.resolve_path(session_id)
        self._last_tail_ids.pop(session_id, None)
        path_key = str(path)
        self._rebuilt.discard(path_key)
        await asyncio.to_thread(lambda: path.unlink(missing_ok=True))

    @staticmethod
    def _read_jsonl_lines(path: Path) -> list[dict[str, Any]]:
        """Read JSONL file; skip empty lines and malformed records."""
        records: list[dict[str, Any]] = []
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        if isinstance(rec, dict):
                            records.append(rec)
                    except json.JSONDecodeError:
                        pass
        except OSError:
            logger.exception("Failed to read JSONL file %s", path)
        return records

    def _sync_read_history(self, path: Path) -> list[dict[str, JSONValue]]:
        """Read and parse JSONL history; strip session_id key from each record."""
        records: list[dict[str, JSONValue]] = []
        for rec in self._read_jsonl_lines(path):
            rec.pop("session_id", None)
            records.append(rec)
        return records

    def _sync_load_jsonl(self, path: Path) -> list[dict[str, Any]]:
        """Read all JSONL records including session_id (needed for multi-session files)."""
        return self._read_jsonl_lines(path)

    def _extract_text(self, record: dict[str, Any]) -> str:
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
        if node_kind == "assistant_response":
            return str(record.get("text", ""))
        if node_kind == "tool_call":
            parts: list[str] = []
            out = record.get("output_text", "")
            if out:
                parts.append(str(out))
            calls = record.get("calls", {})
            if calls:
                parts.append(json.dumps(calls, ensure_ascii=False))
            return " ".join(parts)
        if node_kind == "tool_result":
            results = record.get("results", {})
            return json.dumps(results, ensure_ascii=False) if results else ""
        if node_kind == "summary":
            return str(record.get("summary", ""))
        return ""

    @staticmethod
    def _snippet(text: str, max_len: int = 500) -> str:
        """Truncate text to max_len characters."""
        return text[:max_len]

    def _group_turns(
        self, records: list[dict[str, Any]]
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
        self,
        turns: list[list[dict[str, Any]]],
        q: str,
        limit: int,
    ) -> list[dict[str, JSONValue]]:
        """Return matching turns in reverse-time order."""
        results: list[dict[str, JSONValue]] = []
        for turn in reversed(turns):
            if len(results) >= limit or not turn:
                break
            # Pre-compute (record, text) once per record to avoid double extraction.
            turn_texts = [(rec, self._extract_text(rec)) for rec in turn]
            if q and not any(q in text.lower() for _, text in turn_texts):
                continue
            turn_id = str(turn[0].get("id", ""))
            turn_created = str(turn[0].get("created_at", ""))
            nodes_out: list[JSONValue] = [
                {"kind": str(rec.get("kind", "")), "snippet": self._snippet(text)}
                for rec, text in turn_texts
            ]
            results.append({"turn_id": turn_id, "created_at": turn_created, "nodes": nodes_out})
        return results

    def _search_nodes(
        self,
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
            text = self._extract_text(rec)
            if q and q not in text.lower():
                continue
            node_id = str(rec.get("id", ""))
            results.append(
                {
                    "turn_id": node_to_turn_id.get(node_id, ""),
                    "node_id": node_id,
                    "kind": rec_kind,
                    "created_at": str(rec.get("created_at", "")),
                    "snippet": self._snippet(text),
                }
            )
        return results

    def _filter_records(
        self,
        records: list[dict[str, Any]],
        *,
        query: str,
        kind: str,
        limit: int,
    ) -> list[dict[str, JSONValue]]:
        """Filter records by kind and query, returning results in reverse-time order."""
        turns, node_to_turn_id = self._group_turns(records)
        q = query.lower()
        if kind == "turn":
            return self._search_turns(turns, q, limit)
        return self._search_nodes(records, node_to_turn_id, q, kind, limit)

    async def _search(
        self,
        session_id: str,
        query: str = "",
        kind: str = "turn",
        limit: int = 5,
    ) -> JSONValue:
        """Search session history by keyword."""
        path = self.resolve_path(session_id)
        if not path.exists():
            return []
        all_records = await asyncio.to_thread(self._sync_load_jsonl, path)
        # Filter to this session only (needed for fixed-filename multi-session files).
        records = [r for r in all_records if str(r.get("session_id", "")) == session_id]
        return cast(JSONValue, self._filter_records(records, query=query, kind=kind, limit=limit))

    def __iter__(self) -> Iterator[tuple[str, ToolDef, AsyncToolFn]]:
        """Yield (name, tooldef, fn) triples for registration."""

        async def search_session_fn(args: dict[str, JSONValue]) -> JSONValue:
            from little_agent.agent.context import current_session_id

            session_id = current_session_id.get("-")
            query = str(args.get("query", ""))
            kind = str(args.get("kind", "turn"))
            limit_raw = args.get("limit", 5)
            limit = int(limit_raw) if isinstance(limit_raw, (int, float)) else 5
            return await self._search(session_id, query=query, kind=kind, limit=limit)

        yield ("search_session", _SEARCH_TOOLDEF, search_session_fn)
