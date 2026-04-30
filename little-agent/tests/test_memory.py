"""Tests for memory system."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from little_agent.backends.protocol import BackendTurnResult
from little_agent.memory import FileMemory
from tests.mocks import BuiltinToolProvider, MockAgent, MockBackend, MockClient


class _MemoryBackend(MockBackend):
    """Backend that returns scripted facts for memory extraction."""

    def __init__(self, fact_text: str = "") -> None:
        super().__init__()
        self._fact_text = fact_text

    async def _gen(self, session: object):  # type: ignore[override]
        yield BackendTurnResult(
            output_text=self._fact_text,
            tool_calls=[],
            finish_reason="completed",
        )


@pytest.mark.asyncio
async def test_file_memory_recall_empty(tmp_path: Path) -> None:
    """Empty memory file returns empty recall."""
    mem_path = tmp_path / "memory.jsonl"
    backend = _MemoryBackend()
    memory = FileMemory(backend=backend, path=mem_path)

    result = await memory.recall()
    assert result == ""


@pytest.mark.asyncio
async def test_file_memory_recall_with_facts(tmp_path: Path) -> None:
    """Memory with facts returns formatted summary."""
    mem_path = tmp_path / "memory.jsonl"
    with open(mem_path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"fact": "User likes Python"}, ensure_ascii=False) + "\n")
        f.write(json.dumps({"fact": "User prefers dark mode"}, ensure_ascii=False) + "\n")

    backend = _MemoryBackend()
    memory = FileMemory(backend=backend, path=mem_path)

    result = await memory.recall()
    assert "Important facts from previous conversations:" in result
    assert "User likes Python" in result
    assert "User prefers dark mode" in result


@pytest.mark.asyncio
async def test_file_memory_remember_extracts_facts(tmp_path: Path) -> None:
    """Remember extracts facts from session and persists them."""
    mem_path = tmp_path / "memory.jsonl"
    backend = _MemoryBackend("- User likes Python\n- User prefers dark mode")
    memory = FileMemory(backend=backend, path=mem_path)

    client = MockClient()
    provider = BuiltinToolProvider()
    mock_backend = MockBackend()
    agent = MockAgent(backend=mock_backend, tools=provider, client=client)
    session = await agent.new()

    await session.prompt("hello")
    await memory.remember(session)

    result = await memory.recall()
    assert "User likes Python" in result
    assert "User prefers dark mode" in result

    # Verify file was written
    with open(mem_path, encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    assert len(lines) == 2
    data0 = json.loads(lines[0])
    assert data0["fact"] == "User likes Python"


@pytest.mark.asyncio
async def test_file_memory_remember_none_response(tmp_path: Path) -> None:
    """NONE response from LLM does not add facts."""
    mem_path = tmp_path / "memory.jsonl"
    backend = _MemoryBackend("NONE")
    memory = FileMemory(backend=backend, path=mem_path)

    client = MockClient()
    provider = BuiltinToolProvider()
    mock_backend = MockBackend()
    agent = MockAgent(backend=mock_backend, tools=provider, client=client)
    session = await agent.new()

    await session.prompt("hello")
    await memory.remember(session)

    assert not mem_path.exists()
    result = await memory.recall()
    assert result == ""


@pytest.mark.asyncio
async def test_file_memory_loads_existing_on_init(tmp_path: Path) -> None:
    """FileMemory loads existing facts on initialization."""
    mem_path = tmp_path / "memory.jsonl"
    with open(mem_path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"fact": "Existing fact"}, ensure_ascii=False) + "\n")

    backend = _MemoryBackend()
    memory = FileMemory(backend=backend, path=mem_path)

    result = await memory.recall()
    assert "Existing fact" in result
