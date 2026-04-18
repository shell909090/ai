"""Tests for PlainTextExtractor and PandocExtractor backends."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from tests.test_backends._helpers import _make_module


# ===========================================================================
# PlainTextExtractor
# ===========================================================================


class TestPlainTextExtractor:
    def test_extract_reads_file_content(self, tmp_path: Path) -> None:
        from all2txt.backends.plaintext import PlainTextExtractor

        f = tmp_path / "hello.txt"
        f.write_text("Hello, world!", encoding="utf-8")

        extractor = PlainTextExtractor()
        result = extractor.extract(f)

        assert result == "Hello, world!"

    def test_extract_handles_non_utf8_bytes(self, tmp_path: Path) -> None:
        from all2txt.backends.plaintext import PlainTextExtractor

        f = tmp_path / "binary.txt"
        # Write raw bytes that are not valid UTF-8
        f.write_bytes(b"Hello \xff\xfe World")

        extractor = PlainTextExtractor()
        result = extractor.extract(f)

        # errors="replace" should produce the replacement character instead of raising
        assert "Hello" in result
        assert "\ufffd" in result


# ===========================================================================
# PandocExtractor
# ===========================================================================


class TestPandocExtractor:
    def test_available_returns_false_when_pandoc_missing(self) -> None:
        from all2txt.backends.pandoc import PandocExtractor

        with patch("shutil.which", return_value=None):
            assert PandocExtractor().available() is False

    def test_available_returns_true_when_pandoc_found(self) -> None:
        from all2txt.backends.pandoc import PandocExtractor

        with patch("shutil.which", return_value="/usr/bin/pandoc"):
            assert PandocExtractor().available() is True

    def test_extract_calls_correct_command_and_returns_stdout(self, tmp_path: Path) -> None:
        from all2txt.backends.pandoc import PandocExtractor

        fake_result = MagicMock()
        fake_result.stdout = "extracted text\n"

        with patch("subprocess.run", return_value=fake_result) as mock_run:
            extractor = PandocExtractor()
            result = extractor.extract(tmp_path / "doc.docx")

        mock_run.assert_called_once_with(
            ["pandoc", "-t", "plain", "--wrap=none", str(tmp_path / "doc.docx")],
            capture_output=True,
            text=True,
            check=True,
        )
        assert result == "extracted text\n"

    def test_extract_passes_reader_format_when_mime_known(self, tmp_path: Path) -> None:
        from all2txt.backends.pandoc import PandocExtractor

        fake_result = MagicMock()
        fake_result.stdout = "rst content\n"
        f = tmp_path / "notes.rst"

        with patch("subprocess.run", return_value=fake_result) as mock_run:
            extractor = PandocExtractor(config={"_mime": "text/x-rst"})
            extractor.extract(f)

        cmd = mock_run.call_args[0][0]
        assert "-f" in cmd
        assert cmd[cmd.index("-f") + 1] == "rst"

    def test_extract_omits_reader_when_mime_unknown(self, tmp_path: Path) -> None:
        from all2txt.backends.pandoc import PandocExtractor

        fake_result = MagicMock()
        fake_result.stdout = ""

        with patch("subprocess.run", return_value=fake_result) as mock_run:
            extractor = PandocExtractor(config={"_mime": "application/unknown"})
            extractor.extract(tmp_path / "file.bin")

        cmd = mock_run.call_args[0][0]
        assert "-f" not in cmd
