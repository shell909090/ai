"""Session registry (LRU) and persistence layer."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections import OrderedDict
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from little_agent.types import JSONValue

if TYPE_CHECKING:
    from little_agent.agent.session_store import SessionJSONLStore
    from little_agent.types import Agent, Session

logger = logging.getLogger(__name__)

_UUID4_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


def _is_valid_session_id(session_id: str) -> bool:
    """Return True only for canonical UUID v4 strings."""
    return bool(_UUID4_RE.match(session_id))


_MAX_SESSIONS = 100


class SessionStore:
    """LRU session registry plus disk persistence."""

    def __init__(
        self,
        sessions_dir: Path | None,
        jsonl_store: SessionJSONLStore | None = None,
    ) -> None:
        self._sessions: OrderedDict[str, Session] = OrderedDict()
        self._sessions_dir = sessions_dir
        self._jsonl_store = jsonl_store

    @property
    def sessions_dir(self) -> Path | None:
        """Return the configured sessions directory."""
        return self._sessions_dir

    def register_session(self, session_id: str, session: Session) -> None:
        """Insert or refresh a session in the LRU dict, evicting oldest when over limit."""
        if session_id in self._sessions:
            self._sessions.move_to_end(session_id)
            self._sessions[session_id] = session
        else:
            if len(self._sessions) >= _MAX_SESSIONS:
                evicted_id, _ = self._sessions.popitem(last=False)
                logger.info("Evicted LRU session %s (limit=%d)", evicted_id, _MAX_SESSIONS)
            self._sessions[session_id] = session

    def get_session(self, session_id: str) -> Session | None:
        """Return session and mark as recently used."""
        sess = self._sessions.get(session_id)
        if sess is not None:
            self._sessions.move_to_end(session_id)
        return sess

    def discard_session(self, session_id: str) -> None:
        """Remove a session from the in-memory registry."""
        self._sessions.pop(session_id, None)

    def list_session_ids(self) -> list[str]:
        """Return all in-memory session IDs."""
        return list(self._sessions)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def auto_save(self, session: Session) -> None:
        """Write session.save() as JSON to {sessions_dir}/{session_id}.json."""
        if self._sessions_dir is None:
            return
        try:
            session_id = session.id
            path = self._sessions_dir / f"{session_id}.json"
            data = json.dumps(session.save(), ensure_ascii=False)
            await asyncio.to_thread(self._sync_write_text, path, data)
        except Exception:
            logger.exception("Failed to auto-save session %s", getattr(session, "id", "?"))

    def _sync_write_text(self, path: Path, text: str) -> None:
        """Write text to path, creating parent dirs; called via asyncio.to_thread."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _read_preview(self, session_id: str) -> str:
        """Read first user_prompt record from JSONL and return its prompt (max 50 chars)."""
        if self._jsonl_store is None:
            return ""
        path = self._jsonl_store.resolve_path(session_id)
        if not path.exists():
            return ""
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        if record.get("kind") == "user_prompt":
                            prompt = record.get("prompt", "")
                            if isinstance(prompt, str):
                                return prompt[:50]
                    except json.JSONDecodeError:
                        pass
        except OSError:
            logger.exception("Failed to read preview for session %s", session_id)
        return ""

    async def list_sessions(self) -> list[dict[str, Any]]:
        """List sessions from disk and memory, sorted by updated_at descending."""
        if self._sessions_dir is not None:
            result = await asyncio.to_thread(self._sync_scan_sessions_dir)
        else:
            result = {}
        for sid in self.list_session_ids():
            if sid not in result:
                result[sid] = {
                    "id": sid,
                    "updated_at": datetime.now(UTC).isoformat(),
                    "preview": "",
                }
        return sorted(result.values(), key=lambda x: x["updated_at"], reverse=True)

    def _sync_scan_sessions_dir(self) -> dict[str, dict[str, Any]]:
        """Scan sessions_dir for .json files; called via asyncio.to_thread."""
        result: dict[str, dict[str, Any]] = {}
        if self._sessions_dir is None or not self._sessions_dir.exists():
            return result
        for json_path in self._sessions_dir.glob("*.json"):
            try:
                raw = json.loads(json_path.read_text(encoding="utf-8"))
                sid = raw.get("id")
                if not isinstance(sid, str) or not _is_valid_session_id(sid):
                    continue
                mtime = json_path.stat().st_mtime
                updated_at = datetime.fromtimestamp(mtime, tz=UTC).isoformat()
                preview = self._read_preview(sid)
                result[sid] = {"id": sid, "updated_at": updated_at, "preview": preview}
            except Exception:
                logger.exception("Failed to read session file %s", json_path)
        return result

    async def resume_session(self, agent: Agent, session_id: str) -> Session | None:
        """Return session from memory or load from disk JSON. None if not found."""
        cached = self.get_session(session_id)
        if cached is not None:
            return cached
        if self._sessions_dir is None:
            return None
        path = self._sessions_dir / f"{session_id}.json"
        if not path.exists():
            return None
        try:
            text = await asyncio.to_thread(path.read_text, "utf-8")
            data: JSONValue = json.loads(text)
            return await agent.load(data)
        except Exception:
            logger.exception("Failed to load session %s from disk", session_id)
            return None

    async def read_history(self, session_id: str) -> list[dict[str, Any]]:
        """Read JSONL history for session_id via SessionJSONLStore."""
        if self._jsonl_store is None:
            return []
        return await self._jsonl_store.load_history(session_id)

    async def delete_session(self, session_id: str) -> None:
        """Remove session from memory and delete both disk files."""
        self.discard_session(session_id)
        if self._sessions_dir is not None:
            json_path = self._sessions_dir / f"{session_id}.json"
            await asyncio.to_thread(self._sync_delete_files, json_path)
        if self._jsonl_store is not None:
            await self._jsonl_store.delete_session(session_id)

    def _sync_delete_files(self, *paths: Path) -> None:
        """Unlink files, ignoring missing; called via asyncio.to_thread."""
        for p in paths:
            try:
                p.unlink(missing_ok=True)
            except Exception:
                logger.exception("Failed to delete %s", p)
