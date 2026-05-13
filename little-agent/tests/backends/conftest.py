"""Shared fixtures and helpers for backend tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import MagicMock

from little_agent.agent.protocol import SessionUpdate
from little_agent.backends.protocol import BackendTurnResult


async def _collect(
    gen: AsyncIterator[Any],
) -> tuple[BackendTurnResult, list[SessionUpdate]]:
    """Consume a generate() iterator, returning (result, updates)."""
    updates: list[SessionUpdate] = []
    result: BackendTurnResult | None = None
    async for item in gen:
        if isinstance(item, BackendTurnResult):
            result = item
        else:
            updates.append(item)
    assert result is not None
    return result, updates


class _FakeStream:
    """Minimal fake OpenAI streaming response."""

    def __init__(self, chunks: list[Any]) -> None:
        self._chunks = chunks
        self._pos = 0

    def __aiter__(self) -> "_FakeStream":
        return self

    async def __anext__(self) -> Any:
        if self._pos >= len(self._chunks):
            raise StopAsyncIteration
        chunk = self._chunks[self._pos]
        self._pos += 1
        return chunk


def _make_finish_chunk() -> Any:
    """Build a minimal finish-reason chunk that closes the stream."""
    chunk = MagicMock()
    chunk.choices = [MagicMock()]
    chunk.choices[0].delta.content = None
    chunk.choices[0].delta.tool_calls = None
    chunk.choices[0].delta.reasoning_content = None
    chunk.choices[0].finish_reason = "stop"
    chunk.usage = None
    return chunk
