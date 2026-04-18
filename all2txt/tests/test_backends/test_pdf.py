"""Tests for PyMuPDFExtractor and TikaExtractor backends."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from tests.test_backends._helpers import _make_module


# ===========================================================================
# PyMuPDFExtractor
# ===========================================================================


class TestPyMuPDFExtractor:
    def test_available_returns_false_when_pymupdf_not_importable(self) -> None:
        from all2txt.backends.pymupdf import PyMuPDFExtractor

        with patch.dict(sys.modules, {"pymupdf": None}):
            assert PyMuPDFExtractor().available() is False

    def test_available_returns_true_when_pymupdf_importable(self) -> None:
        from all2txt.backends.pymupdf import PyMuPDFExtractor

        fake_pymupdf = _make_module("pymupdf")
        with patch.dict(sys.modules, {"pymupdf": fake_pymupdf}):
            assert PyMuPDFExtractor().available() is True

    def test_extract_opens_doc_and_joins_pages(self, tmp_path: Path) -> None:
        from all2txt.backends.pymupdf import PyMuPDFExtractor

        fake_page1 = MagicMock()
        fake_page1.get_text.return_value = "Page one text"
        fake_page2 = MagicMock()
        fake_page2.get_text.return_value = "Page two text"

        fake_doc = MagicMock()
        fake_doc.__iter__ = MagicMock(return_value=iter([fake_page1, fake_page2]))

        fake_pymupdf = _make_module("pymupdf")
        fake_pymupdf.open = MagicMock(return_value=fake_doc)

        fake_path = tmp_path / "doc.pdf"
        fake_path.touch()

        with patch.dict(sys.modules, {"pymupdf": fake_pymupdf}):
            extractor = PyMuPDFExtractor()
            result = extractor.extract(fake_path)

        fake_pymupdf.open.assert_called_once_with(str(fake_path))
        fake_doc.close.assert_called_once()
        assert result == "Page one text\n\nPage two text"


# ===========================================================================
# TikaExtractor
# ===========================================================================


class TestTikaExtractor:
    def test_available_returns_false_when_tika_not_importable(self) -> None:
        from all2txt.backends.tika import TikaExtractor

        with patch.dict(sys.modules, {"tika": None}):
            assert TikaExtractor().available() is False

    def test_available_returns_true_when_tika_importable(self) -> None:
        from all2txt.backends.tika import TikaExtractor

        fake_tika = _make_module("tika")
        with patch.dict(sys.modules, {"tika": fake_tika}):
            assert TikaExtractor().available() is True

    def test_extract_calls_parser_and_strips_content(self, tmp_path: Path) -> None:
        from all2txt.backends.tika import TikaExtractor

        fake_path = tmp_path / "doc.pdf"
        fake_path.touch()

        fake_parser = MagicMock()
        fake_parser.from_file.return_value = {"content": "  extracted content  "}

        fake_tika_parser_mod = _make_module("tika.parser")
        fake_tika_parser_mod.from_file = fake_parser.from_file

        fake_tika = _make_module("tika")

        with patch.dict(sys.modules, {"tika": fake_tika, "tika.parser": fake_tika_parser_mod}):
            extractor = TikaExtractor()
            result = extractor.extract(fake_path)

        fake_parser.from_file.assert_called_once_with(str(fake_path))
        assert result == "extracted content"

    def test_extract_returns_empty_string_when_content_is_none(self, tmp_path: Path) -> None:
        from all2txt.backends.tika import TikaExtractor

        fake_path = tmp_path / "empty.pdf"
        fake_path.touch()

        fake_parser = MagicMock()
        fake_parser.from_file.return_value = {"content": None}

        fake_tika_parser_mod = _make_module("tika.parser")
        fake_tika_parser_mod.from_file = fake_parser.from_file

        fake_tika = _make_module("tika")

        with patch.dict(sys.modules, {"tika": fake_tika, "tika.parser": fake_tika_parser_mod}):
            extractor = TikaExtractor()
            result = extractor.extract(fake_path)

        assert result == ""
