"""Tests for SessionStore (LRU registry + persistence)."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from little_agent.agent.session_store import SessionJSONLStore
from little_agent.frontends.web.store import _MAX_SESSIONS, SessionStore


def _make_jsonl_store(tmp_path: Path) -> SessionJSONLStore:
    return SessionJSONLStore(sessions_dir=str(tmp_path))


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
    """read_history delegates to SessionJSONLStore and returns records without session_id."""
    jsonl_store = _make_jsonl_store(tmp_path)
    jsonl = jsonl_store.resolve_path("s1")
    jsonl.write_text(
        json.dumps({"session_id": "s1", "kind": "user_prompt", "id": "n1", "prompt": "hi"}) + "\n",
        encoding="utf-8",
    )
    store = SessionStore(tmp_path, jsonl_store=jsonl_store)
    records = await store.read_history("s1")
    assert len(records) == 1
    assert "session_id" not in records[0]
    assert records[0]["kind"] == "user_prompt"


@pytest.mark.asyncio
async def test_read_history_missing_file(tmp_path: Path) -> None:
    """read_history returns empty list when JSONL file does not exist."""
    jsonl_store = _make_jsonl_store(tmp_path)
    store = SessionStore(tmp_path, jsonl_store=jsonl_store)
    assert await store.read_history("nonexistent") == []


@pytest.mark.asyncio
async def test_read_history_no_jsonl_store() -> None:
    """read_history returns empty list when no jsonl_store is configured."""
    store = SessionStore(None)
    assert await store.read_history("any") == []


@pytest.mark.asyncio
async def test_delete_session_removes_files(tmp_path: Path) -> None:
    """delete_session removes .json and delegates JSONL deletion to SessionJSONLStore."""
    jsonl_store = _make_jsonl_store(tmp_path)
    store = SessionStore(tmp_path, jsonl_store=jsonl_store)
    sess = _make_session("s1")
    store.register_session("s1", sess)
    (tmp_path / "s1.json").write_text("{}", encoding="utf-8")
    jsonl_path = jsonl_store.resolve_path("s1")
    jsonl_path.write_text("", encoding="utf-8")
    await store.delete_session("s1")
    assert not (tmp_path / "s1.json").exists()
    assert not jsonl_path.exists()
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


# ---------------------------------------------------------------------------
# sessions_dir property
# ---------------------------------------------------------------------------


def test_sessions_dir_property(tmp_path: Path) -> None:
    """sessions_dir property returns the configured path."""
    store = SessionStore(tmp_path)
    assert store.sessions_dir is tmp_path


def test_sessions_dir_property_none() -> None:
    """sessions_dir property returns None when not configured."""
    store = SessionStore(None)
    assert store.sessions_dir is None


# ---------------------------------------------------------------------------
# list_sessions: ordering, preview truncation, mtime, missing jsonl
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_sessions_ordering_preview_mtime(tmp_path: Path) -> None:
    """list_sessions: 3 sessions, sorted by mtime desc, preview truncated, updated_at from mtime."""
    jsonl_store = _make_jsonl_store(tmp_path)
    store = SessionStore(tmp_path, jsonl_store=jsonl_store)
    base_time = time.time() - 1000

    sid_old = "00000000-0000-4000-8000-000000000001"
    sid_mid = "00000000-0000-4000-8000-000000000002"
    sid_new = "00000000-0000-4000-8000-000000000003"
    sessions_data = [
        (sid_old, base_time, "Short prompt"),
        (sid_mid, base_time + 300, "A" * 80),
        (sid_new, base_time + 600, "Medium prompt for newest session"),
    ]
    for sid, mtime, prompt_text in sessions_data:
        json_path = tmp_path / f"{sid}.json"
        json_path.write_text(json.dumps({"id": sid}), encoding="utf-8")
        os.utime(json_path, (mtime, mtime))
        jsonl_path = jsonl_store.resolve_path(sid)
        record = {"session_id": sid, "kind": "user_prompt", "id": "n1", "prompt": prompt_text}
        jsonl_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    result = await store.list_sessions()
    ids = [s["id"] for s in result]

    assert ids.index(sid_new) < ids.index(sid_mid) < ids.index(sid_old)

    mid_entry = next(s for s in result if s["id"] == sid_mid)
    assert mid_entry["preview"] == "A" * 50

    new_entry = next(s for s in result if s["id"] == sid_new)
    dt = datetime.fromisoformat(new_entry["updated_at"])
    assert abs(dt.timestamp() - (base_time + 600)) < 2


@pytest.mark.asyncio
async def test_list_sessions_missing_jsonl_empty_preview(tmp_path: Path) -> None:
    """list_sessions returns preview='' when _session.jsonl is absent."""
    store = SessionStore(tmp_path)
    sid = "00000000-0000-4000-8000-000000000004"
    (tmp_path / f"{sid}.json").write_text(json.dumps({"id": sid}), encoding="utf-8")

    result = await store.list_sessions()
    entry = next(s for s in result if s["id"] == sid)
    assert entry["preview"] == ""


@pytest.mark.asyncio
async def test_list_sessions_nonexistent_dir(tmp_path: Path) -> None:
    """list_sessions returns empty list when sessions_dir does not exist."""
    store = SessionStore(tmp_path / "missing")
    result = await store.list_sessions()
    assert result == []


@pytest.mark.asyncio
async def test_list_sessions_invalid_json_files(tmp_path: Path) -> None:
    """list_sessions skips .json files with invalid content or missing id."""
    store = SessionStore(tmp_path)
    (tmp_path / "corrupt.json").write_text("not-json", encoding="utf-8")
    (tmp_path / "noid.json").write_text(json.dumps({"x": 1}), encoding="utf-8")

    result = await store.list_sessions()
    assert all(s["id"] not in ("corrupt", "noid") for s in result)


@pytest.mark.asyncio
async def test_list_sessions_merges_memory_sessions() -> None:
    """list_sessions includes in-memory sessions when no sessions_dir."""
    store = SessionStore(None)
    store.register_session("s_mem", _make_session("s_mem"))

    result = await store.list_sessions()
    assert any(s["id"] == "s_mem" for s in result)


# ---------------------------------------------------------------------------
# _read_preview: OSError via monkeypatch
# ---------------------------------------------------------------------------


def test_read_preview_oserror_returns_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_read_preview returns '' when open raises OSError."""
    store = SessionStore(tmp_path)
    sid = "s_err"
    (tmp_path / f"{sid}_session.jsonl").write_text("content", encoding="utf-8")

    def bad_open(*args: object, **kwargs: object) -> None:
        raise OSError("forced")

    monkeypatch.setattr("builtins.open", bad_open)
    assert store._read_preview(sid) == ""


def test_read_preview_no_sessions_dir() -> None:
    """_read_preview returns '' when sessions_dir is None."""
    store = SessionStore(None)
    assert store._read_preview("any") == ""


# ---------------------------------------------------------------------------
# read_jsonl_lines: OSError, empty lines, invalid JSON
# ---------------------------------------------------------------------------


def test_read_jsonl_lines_oserror_returns_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """read_jsonl_lines returns [] when open raises OSError."""
    from little_agent._utils import read_jsonl_lines

    path = tmp_path / "test.jsonl"
    path.write_text("content", encoding="utf-8")

    def bad_open(*args: object, **kwargs: object) -> None:
        raise OSError("forced")

    monkeypatch.setattr("builtins.open", bad_open)
    assert read_jsonl_lines(path) == []


def test_read_jsonl_lines_skips_empty_and_invalid(tmp_path: Path) -> None:
    """read_jsonl_lines skips empty lines and invalid JSON, returns valid records."""
    from little_agent._utils import read_jsonl_lines

    path = tmp_path / "mixed.jsonl"
    path.write_text(
        "\n" + "not-valid-json\n" + json.dumps({"kind": "summary", "id": "n1"}) + "\n",
        encoding="utf-8",
    )
    records = read_jsonl_lines(path)
    assert len(records) == 1
    assert records[0]["kind"] == "summary"


# ---------------------------------------------------------------------------
# auto_save exception path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_save_exception_does_not_raise(tmp_path: Path) -> None:
    """auto_save catches exception and does not propagate it."""
    store = SessionStore(tmp_path)
    sess = MagicMock()
    sess.id = "s1"
    sess.save.side_effect = RuntimeError("corrupt")
    await store.auto_save(sess)


# ---------------------------------------------------------------------------
# resume_session: None sessions_dir, load exception
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_session_no_sessions_dir_not_cached() -> None:
    """resume_session returns None when sessions_dir is None and session not cached."""
    store = SessionStore(None)
    result = await store.resume_session(MagicMock(), "missing")
    assert result is None


@pytest.mark.asyncio
async def test_resume_session_load_error(tmp_path: Path) -> None:
    """resume_session returns None when agent.load raises."""
    (tmp_path / "s1.json").write_text(json.dumps({"id": "s1"}), encoding="utf-8")
    store = SessionStore(tmp_path)
    agent = MagicMock()
    agent.load = AsyncMock(side_effect=ValueError("corrupt"))
    assert await store.resume_session(agent, "s1") is None


# ---------------------------------------------------------------------------
# read_history: None sessions_dir
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# delete_session: None sessions_dir, _sync_delete_files exception
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_session_no_sessions_dir() -> None:
    """delete_session with None sessions_dir only evicts from memory."""
    store = SessionStore(None)
    store.register_session("s1", _make_session("s1"))
    await store.delete_session("s1")
    assert store.get_session("s1") is None


def test_sync_delete_files_exception(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """_sync_delete_files logs exception but does not raise when unlink fails."""
    store = SessionStore(tmp_path)
    path = tmp_path / "test.json"
    path.write_text("{}", encoding="utf-8")

    def bad_unlink(self: Path, *args: object, **kwargs: object) -> None:
        raise OSError("forced")

    monkeypatch.setattr(Path, "unlink", bad_unlink)
    store._sync_delete_files(path)
