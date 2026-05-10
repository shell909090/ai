"""Tests for SessionStore (LRU registry + persistence)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from little_agent.frontends.web.store import _MAX_SESSIONS, SessionStore


def _make_session(session_id: str) -> MagicMock:
    sess = MagicMock()
    sess.id = session_id
    sess.save.return_value = {"id": session_id, "chain": []}
    return sess


# ---------------------------------------------------------------------------
# LRU registry
# ---------------------------------------------------------------------------


def test_register_and_get_session() -> None:
    """Registered session is retrievable."""
    store = SessionStore(None)
    sess = _make_session("s1")
    store.register_session("s1", sess)
    assert store.get_session("s1") is sess


def test_get_session_none_for_unknown() -> None:
    """get_session returns None for unregistered IDs."""
    store = SessionStore(None)
    assert store.get_session("unknown") is None


def test_lru_eviction_at_limit() -> None:
    """Oldest session is evicted when registry exceeds _MAX_SESSIONS."""
    store = SessionStore(None)
    for i in range(_MAX_SESSIONS):
        store.register_session(f"s{i}", _make_session(f"s{i}"))
    # s0 is oldest; adding one more should evict it
    store.register_session("s_new", _make_session("s_new"))
    assert store.get_session("s0") is None
    assert store.get_session("s_new") is not None
    assert len(store._sessions) == _MAX_SESSIONS


def test_register_refresh_existing() -> None:
    """Re-registering an existing session moves it to most-recent."""
    store = SessionStore(None)
    sess_a = _make_session("a")
    sess_b = _make_session("b")
    store.register_session("a", sess_a)
    store.register_session("b", sess_b)
    # Refresh a — it should now be most-recent; b becomes oldest
    store.register_session("a", sess_a)
    # Fill up to limit + 1: the next insert should evict b, not a
    for i in range(_MAX_SESSIONS - 2):
        store.register_session(f"x{i}", _make_session(f"x{i}"))
    store.register_session("z", _make_session("z"))
    assert store.get_session("b") is None
    assert store.get_session("a") is not None


def test_discard_session() -> None:
    """discard_session removes the session from memory."""
    store = SessionStore(None)
    store.register_session("s1", _make_session("s1"))
    store.discard_session("s1")
    assert store.get_session("s1") is None


def test_list_session_ids() -> None:
    """list_session_ids returns all in-memory IDs."""
    store = SessionStore(None)
    store.register_session("a", _make_session("a"))
    store.register_session("b", _make_session("b"))
    ids = store.list_session_ids()
    assert "a" in ids and "b" in ids


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_save_writes_json(tmp_path: Path) -> None:
    """auto_save writes session JSON to sessions_dir."""
    store = SessionStore(tmp_path)
    sess = _make_session("abc")
    await store.auto_save(sess)
    saved = json.loads((tmp_path / "abc.json").read_text())
    assert saved["id"] == "abc"


@pytest.mark.asyncio
async def test_auto_save_no_sessions_dir() -> None:
    """auto_save is a no-op when sessions_dir is None."""
    store = SessionStore(None)
    sess = _make_session("abc")
    await store.auto_save(sess)  # should not raise


@pytest.mark.asyncio
async def test_read_history_returns_records(tmp_path: Path) -> None:
    """read_history returns parsed JSONL records without session_id key."""
    jsonl = tmp_path / "s1_session.jsonl"
    jsonl.write_text(
        json.dumps({"session_id": "s1", "kind": "user_prompt", "id": "n1", "prompt": "hi"}) + "\n",
        encoding="utf-8",
    )
    store = SessionStore(tmp_path)
    records = await store.read_history("s1")
    assert len(records) == 1
    assert "session_id" not in records[0]
    assert records[0]["kind"] == "user_prompt"


@pytest.mark.asyncio
async def test_read_history_missing_file(tmp_path: Path) -> None:
    """read_history returns empty list when JSONL file does not exist."""
    store = SessionStore(tmp_path)
    assert await store.read_history("nonexistent") == []


@pytest.mark.asyncio
async def test_delete_session_removes_files(tmp_path: Path) -> None:
    """delete_session removes both .json and .jsonl files and evicts from memory."""
    store = SessionStore(tmp_path)
    sess = _make_session("s1")
    store.register_session("s1", sess)
    (tmp_path / "s1.json").write_text("{}", encoding="utf-8")
    (tmp_path / "s1_session.jsonl").write_text("", encoding="utf-8")
    await store.delete_session("s1")
    assert not (tmp_path / "s1.json").exists()
    assert not (tmp_path / "s1_session.jsonl").exists()
    assert store.get_session("s1") is None


@pytest.mark.asyncio
async def test_resume_session_from_memory() -> None:
    """resume_session returns cached session without hitting disk."""
    store = SessionStore(None)
    sess = _make_session("s1")
    store.register_session("s1", sess)
    agent = MagicMock()
    result = await store.resume_session(agent, "s1")
    assert result is sess
    agent.load.assert_not_called()


@pytest.mark.asyncio
async def test_resume_session_from_disk(tmp_path: Path) -> None:
    """resume_session loads session from disk when not in memory."""
    (tmp_path / "s1.json").write_text(json.dumps({"id": "s1", "chain": []}), encoding="utf-8")
    store = SessionStore(tmp_path)
    loaded_sess = _make_session("s1")
    agent = MagicMock()
    agent.load = AsyncMock(return_value=loaded_sess)
    result = await store.resume_session(agent, "s1")
    assert result is loaded_sess


@pytest.mark.asyncio
async def test_resume_session_not_found(tmp_path: Path) -> None:
    """resume_session returns None when session is absent from memory and disk."""
    store = SessionStore(tmp_path)
    agent = MagicMock()
    result = await store.resume_session(agent, "ghost")
    assert result is None
