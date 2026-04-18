"""Tests for ManExtractor and InfoExtractor (system command backends)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch


# ===========================================================================
# ManExtractor
# ===========================================================================


class TestManExtractor:
    def test_available_requires_both_groff_and_col(self) -> None:
        from all2txt.backends.system import ManExtractor

        # Only groff present
        groff_only = lambda x: "/usr/bin/groff" if x == "groff" else None  # noqa: E731
        with patch("shutil.which", side_effect=groff_only):
            assert ManExtractor().available() is False

        # Only col present
        with patch("shutil.which", side_effect=lambda x: "/usr/bin/col" if x == "col" else None):
            assert ManExtractor().available() is False

        # Both present
        with patch("shutil.which", return_value="/usr/bin/tool"):
            assert ManExtractor().available() is True

    def test_extract_pipes_groff_through_col(self, tmp_path: Path) -> None:
        from all2txt.backends.system import ManExtractor

        groff_result = MagicMock()
        groff_result.stdout = b"groff output bytes"

        col_result = MagicMock()
        col_result.stdout = b"plain text output"

        def fake_run(cmd: list[str], **kwargs: Any) -> MagicMock:
            if cmd[0] == "groff":
                return groff_result
            return col_result

        with patch("subprocess.run", side_effect=fake_run) as mock_run:
            extractor = ManExtractor()
            result = extractor.extract(tmp_path / "page.1")

        assert mock_run.call_count == 2
        # First call: groff
        first_call_args = mock_run.call_args_list[0]
        assert first_call_args[0][0][0] == "groff"
        # Second call: col receives groff's stdout
        second_call_args = mock_run.call_args_list[1]
        assert second_call_args[0][0] == ["col", "-bx"]
        assert second_call_args[1]["input"] == groff_result.stdout
        assert result == "plain text output"


# ===========================================================================
# InfoExtractor
# ===========================================================================


class TestInfoExtractor:
    def test_extract_calls_info_with_correct_args(self, tmp_path: Path) -> None:
        from all2txt.backends.system import InfoExtractor

        fake_path = tmp_path / "manual.info"
        fake_result = MagicMock()
        fake_result.stdout = "info content\n"

        with patch("subprocess.run", return_value=fake_result) as mock_run:
            extractor = InfoExtractor()
            result = extractor.extract(fake_path)

        mock_run.assert_called_once_with(
            ["info", "--subnodes", "--output=-", f"--file={fake_path}"],
            capture_output=True,
            text=True,
            check=True,
        )
        assert result == "info content\n"
