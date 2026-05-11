"""Tests for SessionJSONLStore._search() — TASK-D5."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from little_agent.agent.session_store import SessionJSONLStore

SESSION_ID = "test-session-abc"


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")


def _store(tmp_path: Path) -> SessionJSONLStore:
    return SessionJSONLStore(sessions_dir=str(tmp_path))


def _resolve(store: SessionJSONLStore, session_id: str) -> Path:
    return store.resolve_path(session_id)


# ---------------------------------------------------------------------------
# (a) Fixture: multi-turn, multi-kind JSONL
# ---------------------------------------------------------------------------

_TURN1_USER = {
    "session_id": SESSION_ID,
    "id": "t1-user",
    "kind": "user_prompt",
    "created_at": "2024-01-01T00:00:00+00:00",
    "prompt": "hello world",
}
_TURN1_ASSISTANT = {
    "session_id": SESSION_ID,
    "id": "t1-asst",
    "kind": "assistant_response",
    "created_at": "2024-01-01T00:00:01+00:00",
    "text": "hi there",
}
_TURN2_USER = {
    "session_id": SESSION_ID,
    "id": "t2-user",
    "kind": "user_prompt",
    "created_at": "2024-01-01T00:01:00+00:00",
    "prompt": "run bash",
}
_TURN2_TOOL_CALL = {
    "session_id": SESSION_ID,
    "id": "t2-tc",
    "kind": "tool_call",
    "created_at": "2024-01-01T00:01:01+00:00",
    "output_text": "running bash command",
    "calls": {"call-1": {"tool_name": "bash", "arguments": {"command": "ls /tmp"}}},
}
_TURN2_TOOL_RESULT = {
    "session_id": SESSION_ID,
    "id": "t2-tr",
    "kind": "tool_result",
    "created_at": "2024-01-01T00:01:02+00:00",
    "results": {"call-1": {"status": "completed", "content": "file1.txt\nfile2.txt"}},
}
_TURN2_ASSISTANT = {
    "session_id": SESSION_ID,
    "id": "t2-asst",
    "kind": "assistant_response",
    "created_at": "2024-01-01T00:01:03+00:00",
    "text": "done",
}

_ALL_RECORDS = [
    _TURN1_USER,
    _TURN1_ASSISTANT,
    _TURN2_USER,
    _TURN2_TOOL_CALL,
    _TURN2_TOOL_RESULT,
    _TURN2_ASSISTANT,
]


def _write_fixture(store: SessionJSONLStore, records: list[dict[str, Any]] | None = None) -> Path:
    path = _resolve(store, SESSION_ID)
    _write_jsonl(path, records if records is not None else _ALL_RECORDS)
    return path


# ---------------------------------------------------------------------------
# (b) kind=turn: query matches any node in turn → returns full turn
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_turn_query_matches_any_node(tmp_path: Path) -> None:
    """kind=turn: query against one node returns the whole turn."""
    store = _store(tmp_path)
    _write_fixture(store)

    # "hi there" is in turn 1's assistant response
    result = await store._search(SESSION_ID, query="hi there", kind="turn", limit=5)
    assert isinstance(result, list)
    assert len(result) == 1
    turn = result[0]
    assert isinstance(turn, dict)
    assert turn["turn_id"] == "t1-user"
    nodes = turn["nodes"]
    assert isinstance(nodes, list)
    assert len(nodes) == 2
    kinds = [n["kind"] for n in nodes]
    assert "user_prompt" in kinds
    assert "assistant_response" in kinds


@pytest.mark.asyncio
async def test_turn_query_matches_user_prompt(tmp_path: Path) -> None:
    """kind=turn: query matching only the user_prompt still returns full turn."""
    store = _store(tmp_path)
    _write_fixture(store)

    result = await store._search(SESSION_ID, query="hello world", kind="turn", limit=5)
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["turn_id"] == "t1-user"  # type: ignore[index]


# ---------------------------------------------------------------------------
# (c) kind=any: matches any node type, returns single-node shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_any_matches_all_kinds(tmp_path: Path) -> None:
    """kind=any: matches across all node types; each hit is a single node."""
    store = _store(tmp_path)
    _write_fixture(store)

    # "done" only appears in turn2 assistant_response
    result = await store._search(SESSION_ID, query="done", kind="any", limit=5)
    assert isinstance(result, list)
    assert len(result) == 1
    hit = result[0]
    assert isinstance(hit, dict)
    assert hit["node_id"] == "t2-asst"
    assert hit["kind"] == "assistant_response"
    assert "turn_id" in hit
    assert "snippet" in hit


@pytest.mark.asyncio
async def test_any_matches_tool_call(tmp_path: Path) -> None:
    """kind=any: query matches text inside a tool_call node."""
    store = _store(tmp_path)
    _write_fixture(store)

    result = await store._search(SESSION_ID, query="running bash", kind="any", limit=5)
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["node_id"] == "t2-tc"  # type: ignore[index]


# ---------------------------------------------------------------------------
# (d) Specific kind filters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_kind_user_prompt_filters_correctly(tmp_path: Path) -> None:
    """kind=user_prompt returns only user_prompt nodes."""
    store = _store(tmp_path)
    _write_fixture(store)

    result = await store._search(SESSION_ID, query="", kind="user_prompt", limit=10)
    assert isinstance(result, list)
    assert len(result) == 2
    assert all(h["kind"] == "user_prompt" for h in result)  # type: ignore[index]


@pytest.mark.asyncio
async def test_kind_assistant_response_filters_correctly(tmp_path: Path) -> None:
    """kind=assistant_response returns only assistant_response nodes."""
    store = _store(tmp_path)
    _write_fixture(store)

    result = await store._search(SESSION_ID, query="", kind="assistant_response", limit=10)
    assert isinstance(result, list)
    assert len(result) == 2
    assert all(h["kind"] == "assistant_response" for h in result)  # type: ignore[index]


@pytest.mark.asyncio
async def test_kind_tool_call_filters_correctly(tmp_path: Path) -> None:
    """kind=tool_call returns only tool_call nodes."""
    store = _store(tmp_path)
    _write_fixture(store)

    result = await store._search(SESSION_ID, query="", kind="tool_call", limit=10)
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["kind"] == "tool_call"  # type: ignore[index]


@pytest.mark.asyncio
async def test_kind_tool_result_filters_correctly(tmp_path: Path) -> None:
    """kind=tool_result returns only tool_result nodes."""
    store = _store(tmp_path)
    _write_fixture(store)

    result = await store._search(SESSION_ID, query="", kind="tool_result", limit=10)
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["kind"] == "tool_result"  # type: ignore[index]


# ---------------------------------------------------------------------------
# (e) limit boundary and time-descending order
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_limit_caps_results(tmp_path: Path) -> None:
    """Results are capped at the limit parameter."""
    store = _store(tmp_path)
    _write_fixture(store)

    result = await store._search(SESSION_ID, query="", kind="turn", limit=1)
    assert isinstance(result, list)
    assert len(result) == 1


@pytest.mark.asyncio
async def test_turn_results_newest_first(tmp_path: Path) -> None:
    """kind=turn results are returned newest-first."""
    store = _store(tmp_path)
    _write_fixture(store)

    result = await store._search(SESSION_ID, query="", kind="turn", limit=5)
    assert isinstance(result, list)
    assert len(result) == 2
    # turn2 is newer — should be first
    assert result[0]["turn_id"] == "t2-user"  # type: ignore[index]
    assert result[1]["turn_id"] == "t1-user"  # type: ignore[index]


@pytest.mark.asyncio
async def test_node_results_newest_first(tmp_path: Path) -> None:
    """kind=any results are returned newest-first."""
    store = _store(tmp_path)
    _write_fixture(store)

    result = await store._search(SESSION_ID, query="", kind="user_prompt", limit=5)
    assert isinstance(result, list)
    assert len(result) == 2
    # t2-user is newer — should be first
    assert result[0]["node_id"] == "t2-user"  # type: ignore[index]
    assert result[1]["node_id"] == "t1-user"  # type: ignore[index]


# ---------------------------------------------------------------------------
# (f) Empty query behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_query_turn_returns_latest_n_turns(tmp_path: Path) -> None:
    """Empty query with kind=turn returns the latest N turns."""
    store = _store(tmp_path)
    _write_fixture(store)

    result = await store._search(SESSION_ID, query="", kind="turn", limit=2)
    assert isinstance(result, list)
    assert len(result) == 2


@pytest.mark.asyncio
async def test_empty_query_any_returns_latest_n_nodes(tmp_path: Path) -> None:
    """Empty query with kind=any returns the latest N nodes."""
    store = _store(tmp_path)
    _write_fixture(store)

    result = await store._search(SESSION_ID, query="", kind="any", limit=3)
    assert isinstance(result, list)
    assert len(result) == 3


# ---------------------------------------------------------------------------
# (g) Missing JSONL file → empty list, no exception
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_jsonl_returns_empty(tmp_path: Path) -> None:
    """_search returns [] when no JSONL file exists for the session."""
    store = _store(tmp_path)
    result = await store._search("nonexistent-session-xyz", query="anything", kind="turn", limit=5)
    assert result == []


# ---------------------------------------------------------------------------
# (h) Truncated / corrupt last line — no exception
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_corrupt_last_line_skipped(tmp_path: Path) -> None:
    """_search skips a truncated last line without raising an exception."""
    store = _store(tmp_path)
    path = _resolve(store, SESSION_ID)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(_TURN1_USER) + "\n")
        f.write(json.dumps(_TURN1_ASSISTANT) + "\n")
        f.write('{"session_id": "' + SESSION_ID + '", "id": "broken"')  # truncated — no closing }

    result = await store._search(SESSION_ID, query="hello", kind="turn", limit=5)
    assert isinstance(result, list)
    assert len(result) == 1  # only the valid turn


# ---------------------------------------------------------------------------
# (i) Snippet truncated to 500 characters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_snippet_truncated_to_500_chars(tmp_path: Path) -> None:
    """Snippets in search results are at most 500 characters."""
    long_text = "x" * 1000
    records = [
        {
            "session_id": SESSION_ID,
            "id": "long-user",
            "kind": "user_prompt",
            "created_at": "2024-01-01T00:00:00+00:00",
            "prompt": long_text,
        }
    ]
    store = _store(tmp_path)
    _write_fixture(store, records)

    result = await store._search(SESSION_ID, query="", kind="turn", limit=5)
    assert isinstance(result, list)
    assert len(result) == 1
    turn = result[0]
    assert isinstance(turn, dict)
    nodes = turn["nodes"]
    assert isinstance(nodes, list)
    snippet = nodes[0]["snippet"]
    assert isinstance(snippet, str)
    assert len(snippet) <= 500


# ---------------------------------------------------------------------------
# Case-insensitive matching
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_case_insensitive(tmp_path: Path) -> None:
    """Query matching is case-insensitive."""
    store = _store(tmp_path)
    _write_fixture(store)

    result_lower = await store._search(SESSION_ID, query="hello world", kind="turn", limit=5)
    result_upper = await store._search(SESSION_ID, query="HELLO WORLD", kind="turn", limit=5)
    assert result_lower == result_upper
    assert len(result_lower) == 1  # type: ignore[arg-type]
