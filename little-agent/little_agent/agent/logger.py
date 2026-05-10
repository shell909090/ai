"""SessionLogger protocol and FileLogger implementation."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Protocol

from little_agent.agent.nodes import SummaryNode

logger = logging.getLogger(__name__)

_MAX_LOCKS: int = 1024


class SessionLogger(Protocol):
    """Protocol for session event loggers."""

    async def log(self, session: Any) -> None: ...


class FileLogger:
    """Appends session nodes to JSONL file(s), skipping SummaryNode."""

    def __init__(self, filename_template: str) -> None:
        self._template = filename_template
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
        """Expand ~ and substitute {session_id}."""
        return Path(self._template.format(session_id=session_id)).expanduser()

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
            logger.exception("Failed to scan FileLogger file %s", path)

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

    async def log(self, session: Any) -> None:
        """Append new nodes from session.tail back to the last logged node."""
        session_id: str = session.id
        path = self._resolve_path(session_id)
        lock = self._get_lock(path)

        # Lazy rebuild: use per-path init lock + double-check to prevent concurrent
        # sessions from skipping the scan before it completes (P0-3).
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
        self._last_tail_ids[session_id] = session.tail.id
