"""Built-in file tool provider."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from little_agent.types import JSONValue

from .protocol import AsyncToolFn, ToolArgDef, ToolDef


class FileToolProvider:
    """Read and write files on the local filesystem."""

    _WRITE_TOOL_DEF = ToolDef(
        desc="Write content to a file, creating parent directories as needed",
        args=[
            ToolArgDef("path", "string", "File path to write", True),
            ToolArgDef("content", "string", "Content to write", True),
            ToolArgDef("encoding", "string", "File encoding, default utf-8", False),
        ],
    )

    _EDIT_TOOL_DEF = ToolDef(
        desc="Replace an exact string in a file",
        args=[
            ToolArgDef("path", "string", "File path to edit", True),
            ToolArgDef("old_str", "string", "Exact string to replace", True),
            ToolArgDef("new_str", "string", "Replacement string", True),
            ToolArgDef("encoding", "string", "File encoding, default utf-8", False),
        ],
    )

    def __iter__(self) -> Iterator[tuple[str, ToolDef, AsyncToolFn]]:
        """Yield write_file and edit_file tool triples."""
        yield ("write_file", self._WRITE_TOOL_DEF, self._write_dispatch)
        yield ("edit_file", self._EDIT_TOOL_DEF, self._edit_dispatch)

    async def _write_dispatch(self, args: dict[str, JSONValue]) -> JSONValue:
        """Write content to a file, creating parent directories as needed."""
        path = args.get("path")
        content = args.get("content")
        if not isinstance(path, str):
            raise ValueError("path must be a string")
        if not isinstance(content, str):
            raise ValueError("content must be a string")

        encoding_val = args.get("encoding")
        encoding = encoding_val if isinstance(encoding_val, str) else "utf-8"

        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(content, encoding=encoding)
            return f"Written {len(content)} bytes to {path}"
        except Exception as e:
            return f"Error writing {path}: {e}"

    async def _edit_dispatch(self, args: dict[str, JSONValue]) -> JSONValue:
        """Replace an exact string in a file."""
        path = args.get("path")
        old_str = args.get("old_str")
        new_str = args.get("new_str")
        if not isinstance(path, str):
            raise ValueError("path must be a string")
        if not isinstance(old_str, str):
            raise ValueError("old_str must be a string")
        if not isinstance(new_str, str):
            raise ValueError("new_str must be a string")

        encoding_val = args.get("encoding")
        encoding = encoding_val if isinstance(encoding_val, str) else "utf-8"

        try:
            content = Path(path).read_text(encoding=encoding)
            if old_str not in content:
                return f"old_str not found in {path}"
            new_content = content.replace(old_str, new_str, 1)
            Path(path).write_text(new_content, encoding=encoding)
            return f"Replaced 1 occurrence in {path}"
        except Exception as e:
            return f"Error editing {path}: {e}"
