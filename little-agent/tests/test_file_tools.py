"""Tests for file tool provider."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from little_agent.agent.tool_manager import ToolManager
from little_agent.tools.file import FileProvider


def _make_manager() -> ToolManager:
    mgr = ToolManager()
    mgr.register(FileProvider())
    return mgr


@pytest.fixture
def mock_session() -> MagicMock:
    """Minimal session mock for direct tool dispatch calls."""
    s = MagicMock()
    s.id = "mock-session"
    return s


def test_file_tool_listed() -> None:
    """FileProvider.__iter__ only yields 'edit', not 'edit_file'."""
    provider = FileProvider()
    tools = {name for name, _tooldef, _ in provider}
    assert "edit" in tools
    assert "edit_file" not in tools


@pytest.mark.asyncio
async def test_no_old_str_no_pos_raises(tmp_path: Path, mock_session: MagicMock) -> None:
    """Omitting both old_str and pos raises ValueError."""
    mgr = _make_manager()
    target = tmp_path / "hello.txt"
    with pytest.raises(ValueError):
        await mgr["edit"]({"path": str(target), "new_str": "hello world"}, mock_session)


@pytest.mark.asyncio
async def test_old_str_replace(tmp_path: Path, mock_session: MagicMock) -> None:
    """old_str mode replaces only the first occurrence of old_str."""
    mgr = _make_manager()
    target = tmp_path / "edit.txt"
    target.write_text("foo bar foo")
    await mgr["edit"]({"path": str(target), "old_str": "foo", "new_str": "baz"}, mock_session)
    assert target.read_text() == "baz bar foo"


@pytest.mark.asyncio
async def test_old_str_delete(tmp_path: Path, mock_session: MagicMock) -> None:
    """new_str='' deletes the first occurrence of old_str from the file."""
    mgr = _make_manager()
    target = tmp_path / "delete.txt"
    target.write_text("hello world")
    await mgr["edit"]({"path": str(target), "old_str": "hello ", "new_str": ""}, mock_session)
    assert target.read_text() == "world"


@pytest.mark.asyncio
async def test_old_str_not_found(tmp_path: Path, mock_session: MagicMock) -> None:
    """old_str absent from file returns a 'not found' string and leaves file unchanged."""
    mgr = _make_manager()
    target = tmp_path / "noedit.txt"
    original = "hello world"
    target.write_text(original)
    result = await mgr["edit"](
        {"path": str(target), "old_str": "missing", "new_str": "x"}, mock_session
    )
    assert isinstance(result, str)
    assert "not found" in result.lower()
    assert target.read_text() == original


@pytest.mark.asyncio
async def test_old_str_create_new_file(tmp_path: Path, mock_session: MagicMock) -> None:
    """create=True + old_str on a missing file: content is '' so old_str not found."""
    mgr = _make_manager()
    target = tmp_path / "newfile.txt"
    result = await mgr["edit"](
        {"path": str(target), "old_str": "anything", "new_str": "x", "create": True}, mock_session
    )
    assert isinstance(result, str)
    assert "not found" in result.lower()


@pytest.mark.asyncio
async def test_pos_prepend(tmp_path: Path, mock_session: MagicMock) -> None:
    """pos=0, len=0 inserts new_str at the beginning of the file."""
    mgr = _make_manager()
    target = tmp_path / "prepend.txt"
    target.write_text("world")
    await mgr["edit"](
        {"path": str(target), "pos": 0, "len": 0, "new_str": "hello "}, mock_session
    )
    assert target.read_text() == "hello world"


@pytest.mark.asyncio
async def test_pos_append(tmp_path: Path, mock_session: MagicMock) -> None:
    """pos=-1, len=0 appends new_str to the end of the file."""
    mgr = _make_manager()
    target = tmp_path / "append.txt"
    target.write_text("hello")
    await mgr["edit"](
        {"path": str(target), "pos": -1, "len": 0, "new_str": " world"}, mock_session
    )
    assert target.read_text() == "hello world"


@pytest.mark.asyncio
async def test_pos_replace_range(tmp_path: Path, mock_session: MagicMock) -> None:
    """pos=N, len=M replaces M characters starting at position N with new_str."""
    mgr = _make_manager()
    target = tmp_path / "replace.txt"
    target.write_text("hello world")
    await mgr["edit"](
        {"path": str(target), "pos": 6, "len": 5, "new_str": "there"}, mock_session
    )
    assert target.read_text() == "hello there"


@pytest.mark.asyncio
async def test_pos_create_new_file(tmp_path: Path, mock_session: MagicMock) -> None:
    """create=True + pos=0, len=0 on a missing file writes new_str as the full content."""
    mgr = _make_manager()
    target = tmp_path / "newpos.txt"
    await mgr["edit"](
        {"path": str(target), "pos": 0, "len": 0, "new_str": "brand new", "create": True},
        mock_session,
    )
    assert target.exists()
    assert target.read_text() == "brand new"


@pytest.mark.asyncio
async def test_old_str_and_pos_raises(tmp_path: Path, mock_session: MagicMock) -> None:
    """Providing both old_str and pos raises ValueError."""
    mgr = _make_manager()
    target = tmp_path / "conflict.txt"
    target.write_text("some content")
    with pytest.raises(ValueError):
        await mgr["edit"](
            {"path": str(target), "old_str": "some", "pos": 0, "new_str": "other"}, mock_session
        )


@pytest.mark.asyncio
async def test_path_not_string_raises(mock_session: MagicMock) -> None:
    """path=123 (non-string) raises ValueError."""
    mgr = _make_manager()
    with pytest.raises(ValueError):
        await mgr["edit"]({"path": 123, "new_str": "data"}, mock_session)


@pytest.mark.asyncio
async def test_new_str_not_string_raises(tmp_path: Path, mock_session: MagicMock) -> None:
    """new_str=123 (non-string) raises ValueError."""
    mgr = _make_manager()
    target = tmp_path / "test.txt"
    target.write_text("content")
    with pytest.raises(ValueError):
        await mgr["edit"]({"path": str(target), "new_str": 123}, mock_session)


@pytest.mark.asyncio
async def test_pos_negative_len_returns_error(tmp_path: Path, mock_session: MagicMock) -> None:
    """Negative len returns an error string and leaves the file unchanged."""
    mgr = _make_manager()
    target = tmp_path / "neg.txt"
    original = "hello world"
    target.write_text(original)
    result = await mgr["edit"](
        {"path": str(target), "pos": 5, "len": -3, "new_str": "x"}, mock_session
    )
    assert isinstance(result, str)
    assert "error" in result.lower()
    assert target.read_text() == original
