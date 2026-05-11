"""SessionJSONLStore: Hook + ToolProvider that persists session nodes to JSONL files."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

from little_agent.tools.protocol import AsyncToolFn, ToolArgDef, ToolDef
from little_agent.types import JSONValue

from .hooks import Hook

if TYPE_CHECKING:
    from little_agent.agent.protocol import Session

logger = logging.getLogger(__name__)

_MAX_LOCKS: int = 1024

_SEARCH_TOOLDEF = ToolDef(
    desc=(
        "Search this session's history (including turns evicted from active context) by keyword"
    ),
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
        self._last_tail_ids: dict[str, str] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._init_locks: dict[str, asyncio.Lock] = {}
        self._rebuilt: set[str] = set()

        # For fixed filenames (no {session_id}), rebuild last_tail_ids at init time.
        # Called synchronously here because no event loop exists at startup.
        if "{session_id}" not in filename_template:
            path = self._resolve_path("")
            if path.exists():
                self._scan_file(path)
            self._rebuilt.add(str(path))

    def _resolve_path(self, session_id: str) -> Path:
        """Expand ~ and substitute {session_id} in the filename template."""
        filename = self._filename_template.format(session_id=session_id)
        return self._sessions_dir / filename

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
                            self._last_tail_ids[sid] = node_id
                    except json.JSONDecodeError:
                        pass
        except OSError:
            logger.exception("Failed to scan SessionJSONLStore file %s", path)

    def _sync_append(self, path: Path, nodes: list[Any], session_id: str) -> None:
        """Append serialised nodes to path; called via asyncio.to_thread inside the lock."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            for n in nodes:
                record: dict[str, Any] = {
                    "session_id": session_id,
                    "created_at": n.created_at.isoformat(),
                    **n.to_dict(),
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    async def on_turn_end(self, session: "Session") -> None:
        """Append new nodes from session.tail back to the last logged node."""
        from little_agent.agent.nodes import SummaryNode

        session_id: str = session.id
        path = self._resolve_path(session_id)
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
            self._last_tail_ids[session_id] = tail_id

    async def load_history(self, session_id: str) -> list[dict[str, JSONValue]]:
        """Read JSONL file for session_id and return list of records without session_id key."""
        path = self._resolve_path(session_id)
        if not path.exists():
            return []
        return await asyncio.to_thread(self._sync_read_history, path)

    def _sync_read_history(self, path: Path) -> list[dict[str, JSONValue]]:
        """Read and parse JSONL history; called via asyncio.to_thread."""
        records: list[dict[str, JSONValue]] = []
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record: dict[str, JSONValue] = json.loads(line)
                        record.pop("session_id", None)
                        records.append(record)
                    except json.JSONDecodeError:
                        pass
        except OSError:
            logger.exception("Failed to load history from %s", path)
        return records

    async def _search(
        self,
        session_id: str,
        query: str = "",
        kind: str = "turn",
        limit: int = 5,
    ) -> JSONValue:
        """Search session history by keyword."""
        raise NotImplementedError("session search to be implemented in TASK-D5")

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
