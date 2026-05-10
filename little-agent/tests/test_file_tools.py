"""Tests for file tool provider."""

from __future__ import annotations

from pathlib import Path

import pytest

from little_agent.tools.file import FileToolProvider
from little_agent.tools.manager import ToolManager


def _make_manager() -> ToolManager:
    mgr = ToolManager()
    mgr.register(FileToolProvider())
    return mgr


def test_file_tools_listed() -> None:
    """FileToolProvider.__iter__ yields both 'write_file' and 'edit_file' tools."""
    provider = FileToolProvider()
    tools = {name: tooldef for name, tooldef, _ in provider}
    assert "write_file" in tools
    assert "edit_file" in tools


@pytest.mark.asyncio
async def test_write_file_creates_file(tmp_path: Path) -> None:
    """write_file creates the file with the given content."""
    mgr = _make_manager()
    target = tmp_path / "hello.txt"
    await mgr["write_file"]({"path": str(target), "content": "hello world"})
    assert target.exists()
    assert target.read_text() == "hello world"


@pytest.mark.asyncio
async def test_write_file_creates_parent_dirs(tmp_path: Path) -> None:
    """write_file creates intermediate parent directories automatically."""
    mgr = _make_manager()
    target = tmp_path / "a" / "b" / "c" / "file.txt"
    await mgr["write_file"]({"path": str(target), "content": "nested"})
    assert target.exists()
    assert target.read_text() == "nested"


@pytest.mark.asyncio
async def test_write_file_returns_message(tmp_path: Path) -> None:
    """write_file return value contains 'Written' and the file path."""
    mgr = _make_manager()
    target = tmp_path / "out.txt"
    result = await mgr["write_file"]({"path": str(target), "content": "data"})
    assert isinstance(result, str)
    assert "Written" in result
    assert str(target) in result


@pytest.mark.asyncio
async def test_write_file_overwrites(tmp_path: Path) -> None:
    """write_file overwrites existing content on a second call."""
    mgr = _make_manager()
    target = tmp_path / "overwrite.txt"
    await mgr["write_file"]({"path": str(target), "content": "first"})
    await mgr["write_file"]({"path": str(target), "content": "second"})
    assert target.read_text() == "second"


@pytest.mark.asyncio
async def test_edit_file_replaces_first_occurrence(tmp_path: Path) -> None:
    """edit_file replaces only the first occurrence of old_str."""
    mgr = _make_manager()
    target = tmp_path / "edit.txt"
    target.write_text("foo bar foo")
    await mgr["edit_file"]({"path": str(target), "old_str": "foo", "new_str": "baz"})
    assert target.read_text() == "baz bar foo"


@pytest.mark.asyncio
async def test_edit_file_old_str_not_found(tmp_path: Path) -> None:
    """edit_file returns a 'not found' message and leaves the file unchanged."""
    mgr = _make_manager()
    target = tmp_path / "noedit.txt"
    original = "hello world"
    target.write_text(original)
    result = await mgr["edit_file"]({"path": str(target), "old_str": "missing", "new_str": "x"})
    assert isinstance(result, str)
    assert "not found" in result.lower()
    assert target.read_text() == original


@pytest.mark.asyncio
async def test_edit_file_invalid_path_type() -> None:
    """edit_file raises ValueError when path is not a string."""
    mgr = _make_manager()
    with pytest.raises(ValueError):
        await mgr["edit_file"]({"path": 123, "old_str": "a", "new_str": "b"})


@pytest.mark.asyncio
async def test_write_file_invalid_content_type() -> None:
    """write_file raises ValueError when content is not a string."""
    mgr = _make_manager()
    with pytest.raises(ValueError):
        await mgr["write_file"]({"path": "/tmp/test.txt", "content": 123})
