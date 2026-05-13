"""SessionJSONLStore: Hook that persists session nodes to JSONL files."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from little_agent.types import Hook, JSONValue, Session

logger = logging.getLogger(__name__)

_MAX_LOCKS: int = 1024


class SessionJSONLStore(Hook):
    """Appends session nodes to per-session JSONL files on every turn end."""

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

    @staticmethod
    def _evict_if_full(d: dict[str, Any], key: str) -> None:
        """Evict oldest entry if dict is full and key is new (LRU by insertion order)."""
        if key not in d and len(d) >= _MAX_LOCKS:
            d.pop(next(iter(d)))

    def _set_last_tail_id(self, session_id: str, node_id: str) -> None:
        """Record last tail id; evict oldest entry when cap is reached."""
        self._evict_if_full(self._last_tail_ids, session_id)
        self._last_tail_ids[session_id] = node_id

    def _get_lock(self, path: Path) -> asyncio.Lock:
        """Return (creating if needed) the per-file write lock; evict oldest if at cap."""
        key = str(path)
        if key not in self._locks:
            self._evict_if_full(self._locks, key)
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    def _get_init_lock(self, path: Path) -> asyncio.Lock:
        """Return (creating if needed) the per-path init lock; evict oldest if at cap."""
        key = str(path)
        if key not in self._init_locks:
            self._evict_if_full(self._init_locks, key)
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
        """Append new nodes from end of messages back to the last logged node."""
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

        # Walk from end of messages backwards, collecting nodes until stop_id.
        messages = session.messages
        nodes: list[Any] = []
        for node in reversed(messages):
            if node.id == stop_id:
                break
            nodes.append(node)

        if not nodes:
            return

        nodes.reverse()  # write oldest-first

        async with lock:
            await asyncio.to_thread(self._sync_append, path, nodes, session_id)

        if messages:
            self._set_last_tail_id(session_id, messages[-1].id)

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
        self._rebuilt.discard(str(path))
        await asyncio.to_thread(path.unlink, missing_ok=True)

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
