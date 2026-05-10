"""Tests for FileLogger."""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

import pytest

from little_agent.agent.logger import FileLogger
from little_agent.agent.nodes import (
    AssistantResponseNode,
    SummaryNode,
    UserPromptNode,
)


class _MockSession:
    def __init__(self, session_id: str) -> None:
        self.id = session_id
        self.tail = None


def _make_user_node(node_id: str | None = None, prompt: str = "hello") -> UserPromptNode:
    return UserPromptNode(id=node_id or str(uuid.uuid4()), prompt=prompt)


def _make_assistant_node(node_id: str | None = None, text: str = "world") -> AssistantResponseNode:
    return AssistantResponseNode(id=node_id or str(uuid.uuid4()), text=text)


def _make_summary_node(node_id: str | None = None, summary: str = "summary") -> SummaryNode:
    return SummaryNode(id=node_id or str(uuid.uuid4()), summary=summary)


@pytest.mark.asyncio
async def test_log_writes_nodes_in_order(tmp_path: Path) -> None:
    """FileLogger writes all nodes in chronological order to a fixed-path JSONL file."""
    log_file = tmp_path / "test.jsonl"
    logger = FileLogger(str(log_file))

    node1 = _make_user_node(prompt="first")
    node2 = _make_user_node(prompt="second")
    node1.prev = None
    node2.prev = node1

    session = _MockSession("sess-1")
    session.tail = node2

    await logger.log(session)

    lines = log_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2

    rec0 = json.loads(lines[0])
    rec1 = json.loads(lines[1])

    # Chronological order: node1 (older) first
    assert rec0["id"] == node1.id
    assert rec1["id"] == node2.id

    for rec in (rec0, rec1):
        assert rec["session_id"] == "sess-1"
        assert rec["kind"] == "user_prompt"
        assert "id" in rec
        assert "created_at" in rec


@pytest.mark.asyncio
async def test_log_skips_summary_node(tmp_path: Path) -> None:
    """FileLogger omits SummaryNode records from the output file."""
    log_file = tmp_path / "test.jsonl"
    logger = FileLogger(str(log_file))

    node1 = _make_user_node(prompt="before")
    node2 = _make_summary_node(summary="compressed")
    node3 = _make_assistant_node(text="after")

    node1.prev = None
    node2.prev = node1
    node3.prev = node2

    session = _MockSession("sess-2")
    session.tail = node3

    await logger.log(session)

    lines = log_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2

    kinds = [json.loads(line)["kind"] for line in lines]
    assert "summary" not in kinds
    assert kinds == ["user_prompt", "assistant_response"]


@pytest.mark.asyncio
async def test_log_only_new_nodes_after_second_call(tmp_path: Path) -> None:
    """Second log() call writes only nodes added since the first call."""
    log_file = tmp_path / "test.jsonl"
    logger = FileLogger(str(log_file))

    node_a = _make_user_node(prompt="A")
    node_b = _make_assistant_node(text="B")
    node_c = _make_user_node(prompt="C")

    node_a.prev = None
    node_b.prev = node_a
    node_c.prev = node_b

    session = _MockSession("sess-3")
    session.tail = node_c

    await logger.log(session)

    lines = log_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3

    # Add a new node D and advance the tail
    node_d = _make_assistant_node(text="D")
    node_d.prev = node_c
    session.tail = node_d

    await logger.log(session)

    lines = log_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4
    last_rec = json.loads(lines[-1])
    assert last_rec["id"] == node_d.id


@pytest.mark.asyncio
async def test_rebuild_on_startup(tmp_path: Path) -> None:
    """FileLogger restores _last_tail_ids from an existing JSONL file at init."""
    log_file = tmp_path / "existing.jsonl"

    records = [
        {
            "session_id": "s1",
            "id": "node-first",
            "kind": "user_prompt",
            "created_at": "2024-01-01T00:00:00+00:00",
        },
        {
            "session_id": "s1",
            "id": "node-last",
            "kind": "user_prompt",
            "created_at": "2024-01-01T00:01:00+00:00",
        },
    ]
    log_file.write_text(
        "\n".join(json.dumps(r) for r in records) + "\n",
        encoding="utf-8",
    )

    logger = FileLogger(str(log_file))

    assert logger._last_tail_ids.get("s1") == "node-last"


@pytest.mark.asyncio
async def test_per_session_files_lazy_rebuild(tmp_path: Path) -> None:
    """Per-session FileLogger skips already-written nodes via lazy rebuild."""
    session_file = tmp_path / "session_s1.jsonl"
    existing_record = {
        "session_id": "s1",
        "id": "existing-node",
        "kind": "user_prompt",
        "created_at": "2024-01-01T00:00:00+00:00",
        "prompt": "old",
    }
    session_file.write_text(json.dumps(existing_record) + "\n", encoding="utf-8")

    template = str(tmp_path / "session_{session_id}.jsonl")
    logger = FileLogger(template)

    existing_node = _make_user_node(node_id="existing-node", prompt="old")
    new_node = _make_user_node(node_id="new-node", prompt="new")

    existing_node.prev = None
    new_node.prev = existing_node

    session = _MockSession("s1")
    session.tail = new_node

    await logger.log(session)

    lines = session_file.read_text(encoding="utf-8").splitlines()
    # Only the new record should have been appended (1 pre-existing + 1 new = 2 total)
    assert len(lines) == 2
    new_rec = json.loads(lines[-1])
    assert new_rec["id"] == "new-node"


@pytest.mark.asyncio
async def test_concurrent_log_same_file(tmp_path: Path) -> None:
    """Concurrent log() calls on the same file produce 6 valid, non-corrupted records."""
    log_file = tmp_path / "concurrent.jsonl"
    logger = FileLogger(str(log_file))

    sessions = []
    for i in range(3):
        node1 = _make_user_node(prompt=f"session-{i}-node-1")
        node2 = _make_assistant_node(text=f"session-{i}-node-2")
        node1.prev = None
        node2.prev = node1

        s = _MockSession(f"sess-concurrent-{i}")
        s.tail = node2
        sessions.append(s)

    await asyncio.gather(*[logger.log(s) for s in sessions])

    lines = log_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 6

    # Verify every line is valid JSON with required fields
    for line in lines:
        rec = json.loads(line)
        assert "session_id" in rec
        assert "id" in rec
        assert "kind" in rec
        assert "created_at" in rec
