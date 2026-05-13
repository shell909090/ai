"""Built-in file tool provider."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from little_agent.types import AsyncToolFn, JSONValue, Session

from .protocol import ToolArgDef, ToolDef


class EditFileToolProvider:
    """Read and write files on the local filesystem."""

    def __init__(self, **kwargs: object) -> None:
        """Create EditFileToolProvider. Accepts no configuration kwargs."""

    _EDIT_TOOL_DEF = ToolDef(
        desc=(
            "Edit a file. Three mutually exclusive modes: "
            "(1) full overwrite — omit both old_str and pos, file is replaced by new_str; "
            "(2) string mode — set old_str to locate target (first occurrence), "
            "new_str='' deletes; returns error and leaves file unchanged if old_str absent; "
            "(3) position mode — set pos (0-indexed char offset, -1 = end of file) "
            "and optionally len (chars to replace at pos; 0 = pure insert)."
        ),
        args=[
            ToolArgDef("path", "string", "File path", True),
            ToolArgDef(
                "new_str",
                "string",
                "Content to write/insert/replace (empty string = delete)",
                True,
            ),
            ToolArgDef(
                "old_str",
                "string",
                "Exact string to locate (first occurrence). Replaced with new_str. "
                "Returns error if absent; mutually exclusive with pos.",
                False,
            ),
            ToolArgDef(
                "pos",
                "integer",
                "Character position (0-indexed, -1 = end of file). "
                "Use with len. Mutually exclusive with old_str.",
                False,
            ),
            ToolArgDef(
                "len",
                "integer",
                "With pos: chars at pos to replace; 0 = pure insert. Default 0.",
                False,
            ),
            ToolArgDef(
                "create",
                "boolean",
                "If true and file is missing, create it and parent directories. "
                "If false (default), missing file returns an error.",
                False,
            ),
            ToolArgDef("encoding", "string", "File encoding, default utf-8", False),
        ],
    )

    def __iter__(self) -> Iterator[tuple[str, ToolDef, AsyncToolFn]]:
        """Yield edit_file tool triple."""
        yield ("edit_file", self._EDIT_TOOL_DEF, self._edit_dispatch)

    def _validate(
        self, args: dict[str, JSONValue]
    ) -> tuple[str, str, str | None, JSONValue, JSONValue, bool, str]:
        """Validate and extract args; raise ValueError on bad input."""
        path = args.get("path")
        new_str = args.get("new_str")
        old_str = args.get("old_str")
        pos = args.get("pos")

        if not isinstance(path, str):
            raise ValueError("path must be a string")
        if not isinstance(new_str, str):
            raise ValueError("new_str must be a string")
        if old_str is not None and not isinstance(old_str, str):
            raise ValueError("old_str must be a string")
        if old_str is not None and pos is not None:
            raise ValueError("old_str and pos are mutually exclusive")

        encoding_val = args.get("encoding")
        encoding = encoding_val if isinstance(encoding_val, str) else "utf-8"

        create_val = args.get("create")
        create = bool(create_val) if isinstance(create_val, bool) else False

        return path, new_str, old_str, pos, args.get("len"), create, encoding

    def _apply_op(
        self,
        content: str,
        new_str: str,
        old_str: str | None,
        pos: JSONValue,
        len_val: JSONValue,
    ) -> tuple[str, str | None]:
        """Apply edit operation; return (new_content, error_message_or_None)."""
        if old_str is None and pos is None:
            return new_str, None
        if old_str is not None:
            if old_str not in content:
                return content, "old_str not found"
            return content.replace(old_str, new_str, 1), None
        int_pos = int(pos)  # type: ignore[arg-type]
        if int_pos < -1:
            raise ValueError(f"pos must be >= -1, got {int_pos}")
        actual_pos = len(content) if int_pos == -1 else int_pos
        if actual_pos > len(content):
            raise ValueError(f"pos {int_pos} exceeds file length {len(content)}")
        actual_len = int(len_val) if isinstance(len_val, int) else 0
        if actual_len < 0:
            raise ValueError("len must be non-negative")
        return content[:actual_pos] + new_str + content[actual_pos + actual_len :], None

    async def _edit_dispatch(self, args: dict[str, JSONValue], session: Session) -> JSONValue:
        """Create, overwrite, or partially edit a file."""
        path, new_str, old_str, pos, len_val, create, encoding = self._validate(args)

        p = Path(path)
        if not p.exists():
            if not create:
                return f"File not found: {path}"
            p.parent.mkdir(parents=True, exist_ok=True)
            content = ""
        else:
            content = p.read_text(encoding=encoding)

        try:
            new_content, err = self._apply_op(content, new_str, old_str, pos, len_val)
            if err:
                return f"{err} in {path}"
            p.write_text(new_content, encoding=encoding)
            return f"Edited {path}"
        except Exception as e:
            return f"Error editing {path}: {e}"
