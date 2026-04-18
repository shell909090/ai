"""Unit tests for all2txt backends.

All external tools and optional libraries are mocked; no real subprocess calls
or network requests are made.
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_module(name: str, **attrs: Any) -> ModuleType:
    """Create a minimal fake module and insert it (plus parent packages) into sys.modules."""
    parts = name.split(".")
    for i in range(1, len(parts) + 1):
        key = ".".join(parts[:i])
        if key not in sys.modules:
            mod = ModuleType(key)
            sys.modules[key] = mod
        else:
            mod = sys.modules[key]
    # Set attributes on the leaf module
    for k, v in attrs.items():
        setattr(mod, k, v)
    return mod


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


# ===========================================================================
# LibreOfficeExtractor
# ===========================================================================


class TestLibreOfficeExtractor:
    def test_available_checks_libreoffice_binary(self) -> None:
        from all2txt.backends.libreoffice import LibreOfficeExtractor

        with patch("shutil.which", return_value=None):
            assert LibreOfficeExtractor().available() is False

        lo_only = lambda x: "/usr/bin/libreoffice" if x == "libreoffice" else None  # noqa: E731
        with patch("shutil.which", side_effect=lo_only):
            assert LibreOfficeExtractor().available() is True

    def test_available_checks_soffice_binary(self) -> None:
        from all2txt.backends.libreoffice import LibreOfficeExtractor

        # libreoffice absent but soffice present
        so_only = lambda x: "/usr/bin/soffice" if x == "soffice" else None  # noqa: E731
        with patch("shutil.which", side_effect=so_only):
            assert LibreOfficeExtractor().available() is True

    def test_extract_runs_libreoffice_reads_output_and_cleans_up(self, tmp_path: Path) -> None:
        from all2txt.backends.libreoffice import LibreOfficeExtractor

        input_path = tmp_path / "report.docx"
        input_path.touch()

        # We need a real tmpdir that will contain the output .txt
        import tempfile

        real_tmpdir = tempfile.mkdtemp()
        out_txt = Path(real_tmpdir) / "report.txt"
        out_txt.write_text("LibreOffice extracted text", encoding="utf-8")

        with (
            patch("shutil.which", return_value="/usr/bin/libreoffice"),
            patch("tempfile.mkdtemp", return_value=real_tmpdir),
            patch("subprocess.run") as mock_run,
            patch("shutil.rmtree") as mock_rmtree,
        ):
            extractor = LibreOfficeExtractor()
            result = extractor.extract(input_path)

        mock_run.assert_called_once_with(
            [
                "/usr/bin/libreoffice",
                "--headless",
                "--convert-to",
                "txt:Text",
                "--outdir",
                real_tmpdir,
                str(input_path),
            ],
            capture_output=True,
            check=True,
        )
        mock_rmtree.assert_called_once_with(real_tmpdir, ignore_errors=True)
        assert result == "LibreOffice extracted text"

    def test_extract_cleans_up_on_failure(self, tmp_path: Path) -> None:
        from all2txt.backends.libreoffice import LibreOfficeExtractor

        input_path = tmp_path / "broken.docx"
        input_path.touch()

        import tempfile

        real_tmpdir = tempfile.mkdtemp()

        with (
            patch("shutil.which", return_value="/usr/bin/libreoffice"),
            patch("tempfile.mkdtemp", return_value=real_tmpdir),
            patch("subprocess.run", side_effect=RuntimeError("libreoffice failed")),
            patch("shutil.rmtree") as mock_rmtree,
        ):
            extractor = LibreOfficeExtractor()
            with pytest.raises(RuntimeError):
                extractor.extract(input_path)

        mock_rmtree.assert_called_once_with(real_tmpdir, ignore_errors=True)


# ===========================================================================
# NativeDocxExtractor
# ===========================================================================


class TestNativeDocxExtractor:
    def test_available_returns_false_when_docx_not_importable(self) -> None:
        from all2txt.backends.native_office import NativeDocxExtractor

        with patch.dict(sys.modules, {"docx": None}):
            assert NativeDocxExtractor().available() is False

    def test_available_returns_true_when_docx_importable(self) -> None:
        from all2txt.backends.native_office import NativeDocxExtractor

        fake_docx = _make_module("docx")
        fake_docx_ns = _make_module("docx.oxml")
        fake_docx_ns_ns = _make_module("docx.oxml.ns")
        fake_docx_ns_ns.qn = MagicMock()

        with patch.dict(
            sys.modules,
            {"docx": fake_docx, "docx.oxml": fake_docx_ns, "docx.oxml.ns": fake_docx_ns_ns},
        ):
            assert NativeDocxExtractor().available() is True

    def test_extract_joins_paragraphs_and_table_cells(self, tmp_path: Path) -> None:
        from all2txt.backends.native_office import NativeDocxExtractor

        fake_path = tmp_path / "doc.docx"
        fake_path.touch()

        # Build a minimal fake document element tree
        _WML_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

        def make_elem(tag_local: str, ns: str = _WML_NS) -> MagicMock:
            el = MagicMock()
            el.tag = f"{{{ns}}}{tag_local}"
            return el

        # Paragraph element
        p_el = make_elem("p")
        t1 = MagicMock()
        t1.text = "Hello"
        # findall returns wt elements for paragraph
        p_el.findall = MagicMock(return_value=[t1])

        # Table element with one row and one cell
        tbl_el = make_elem("tbl")
        tc_el = MagicMock()
        t2 = MagicMock()
        t2.text = "Cell"
        tc_el.findall = MagicMock(return_value=[t2])
        tr_el = MagicMock()
        tr_el.findall = MagicMock(return_value=[tc_el])
        tbl_el.findall = MagicMock(return_value=[tr_el])

        body_mock = MagicMock()
        body_mock.__iter__ = MagicMock(return_value=iter([p_el, tbl_el]))

        doc_mock = MagicMock()
        doc_mock.element.body = body_mock

        qn_mock = MagicMock(side_effect=lambda s: s)

        fake_docx = _make_module("docx")
        fake_docx.Document = MagicMock(return_value=doc_mock)
        fake_docx_oxml = _make_module("docx.oxml")
        fake_docx_oxml_ns = _make_module("docx.oxml.ns")
        fake_docx_oxml_ns.qn = qn_mock

        with patch.dict(
            sys.modules,
            {
                "docx": fake_docx,
                "docx.oxml": fake_docx_oxml,
                "docx.oxml.ns": fake_docx_oxml_ns,
            },
        ):
            extractor = NativeDocxExtractor()
            result = extractor.extract(fake_path)

        assert "Hello" in result
        assert "Cell" in result


# ===========================================================================
# NativeXlsxExtractor
# ===========================================================================


class TestNativeXlsxExtractor:
    def test_available_returns_false_when_openpyxl_not_importable(self) -> None:
        from all2txt.backends.native_office import NativeXlsxExtractor

        with patch.dict(sys.modules, {"openpyxl": None}):
            assert NativeXlsxExtractor().available() is False

    def test_available_returns_true_when_openpyxl_importable(self) -> None:
        from all2txt.backends.native_office import NativeXlsxExtractor

        fake_openpyxl = _make_module("openpyxl")
        with patch.dict(sys.modules, {"openpyxl": fake_openpyxl}):
            assert NativeXlsxExtractor().available() is True

    def test_extract_joins_rows_and_sheets(self, tmp_path: Path) -> None:
        from all2txt.backends.native_office import NativeXlsxExtractor

        fake_path = tmp_path / "workbook.xlsx"
        fake_path.touch()

        ws1 = MagicMock()
        ws1.iter_rows.return_value = [("A", "B"), ("C", None)]
        ws2 = MagicMock()
        ws2.iter_rows.return_value = [("X",)]

        wb_mock = MagicMock()
        wb_mock.worksheets = [ws1, ws2]

        fake_openpyxl = _make_module("openpyxl")
        fake_openpyxl.load_workbook = MagicMock(return_value=wb_mock)

        with patch.dict(sys.modules, {"openpyxl": fake_openpyxl}):
            extractor = NativeXlsxExtractor()
            result = extractor.extract(fake_path)

        # Sheet 1 has two rows; sheet 2 has one row; separated by blank line
        assert "A\tB" in result
        assert "C\t" in result
        assert "X" in result
        assert "\n\n" in result
        wb_mock.close.assert_called_once()


# ===========================================================================
# NativePptxExtractor
# ===========================================================================


class TestNativePptxExtractor:
    def test_available_returns_false_when_pptx_not_importable(self) -> None:
        from all2txt.backends.native_office import NativePptxExtractor

        with patch.dict(sys.modules, {"pptx": None}):
            assert NativePptxExtractor().available() is False

    def test_available_returns_true_when_pptx_importable(self) -> None:
        from all2txt.backends.native_office import NativePptxExtractor

        fake_pptx = _make_module("pptx")
        with patch.dict(sys.modules, {"pptx": fake_pptx}):
            assert NativePptxExtractor().available() is True

    def test_extract_collects_text_from_slides(self, tmp_path: Path) -> None:
        from all2txt.backends.native_office import NativePptxExtractor

        fake_path = tmp_path / "pres.pptx"
        fake_path.touch()

        run1 = MagicMock()
        run1.text = "Hello"
        run2 = MagicMock()
        run2.text = " world"

        para1 = MagicMock()
        para1.runs = [run1, run2]

        tf = MagicMock()
        tf.paragraphs = [para1]

        shape1 = MagicMock()
        shape1.has_text_frame = True
        shape1.text_frame = tf

        shape2 = MagicMock()
        shape2.has_text_frame = False  # should be skipped

        slide1 = MagicMock()
        slide1.shapes = [shape1, shape2]

        prs_mock = MagicMock()
        prs_mock.slides = [slide1]

        fake_pptx = _make_module("pptx")
        fake_pptx.Presentation = MagicMock(return_value=prs_mock)

        with patch.dict(sys.modules, {"pptx": fake_pptx}):
            extractor = NativePptxExtractor()
            result = extractor.extract(fake_path)

        assert result == "Hello world"


# ===========================================================================
# UnstructuredExtractor
# ===========================================================================


class TestUnstructuredExtractor:
    def test_available_returns_false_when_unstructured_not_importable(self) -> None:
        from all2txt.backends.unstructured import UnstructuredExtractor

        missing = {
            "unstructured": None,
            "unstructured.partition": None,
            "unstructured.partition.auto": None,
        }
        with patch.dict(sys.modules, missing):
            assert UnstructuredExtractor().available() is False

    def test_available_returns_true_when_unstructured_importable(self) -> None:
        from all2txt.backends.unstructured import UnstructuredExtractor

        fake_auto = _make_module("unstructured.partition.auto")
        fake_auto.partition = MagicMock()
        fake_partition = _make_module("unstructured.partition")
        fake_unstructured = _make_module("unstructured")

        with patch.dict(
            sys.modules,
            {
                "unstructured": fake_unstructured,
                "unstructured.partition": fake_partition,
                "unstructured.partition.auto": fake_auto,
            },
        ):
            assert UnstructuredExtractor().available() is True

    def test_extract_partitions_file_and_joins_elements(self, tmp_path: Path) -> None:
        from all2txt.backends.unstructured import UnstructuredExtractor

        fake_path = tmp_path / "doc.pdf"
        fake_path.touch()

        el1 = MagicMock()
        el1.__str__ = MagicMock(return_value="Element one")
        el2 = MagicMock()
        el2.__str__ = MagicMock(return_value="Element two")

        fake_auto = _make_module("unstructured.partition.auto")
        fake_auto.partition = MagicMock(return_value=[el1, el2])
        fake_partition = _make_module("unstructured.partition")
        fake_unstructured = _make_module("unstructured")

        with patch.dict(
            sys.modules,
            {
                "unstructured": fake_unstructured,
                "unstructured.partition": fake_partition,
                "unstructured.partition.auto": fake_auto,
            },
        ):
            extractor = UnstructuredExtractor()
            result = extractor.extract(fake_path)

        fake_auto.partition.assert_called_once_with(filename=str(fake_path))
        assert result == "Element one\nElement two"


# ===========================================================================
# TesseractExtractor
# ===========================================================================


class TestTesseractExtractor:
    def test_available_returns_false_when_pytesseract_not_importable(self) -> None:
        from all2txt.backends.ocr import TesseractExtractor

        with patch.dict(sys.modules, {"pytesseract": None}):
            assert TesseractExtractor().available() is False

    def test_available_returns_true_when_pytesseract_importable(self) -> None:
        from all2txt.backends.ocr import TesseractExtractor

        fake_pt = _make_module("pytesseract")
        with patch.dict(sys.modules, {"pytesseract": fake_pt}):
            assert TesseractExtractor().available() is True

    def test_extract_uses_config_lang_and_psm(self, tmp_path: Path) -> None:
        from all2txt.backends.ocr import TesseractExtractor

        fake_path = tmp_path / "image.png"
        fake_path.touch()

        fake_img = MagicMock()

        fake_pt = _make_module("pytesseract")
        fake_pt.image_to_string = MagicMock(return_value="OCR result")

        fake_pil_image = MagicMock()
        fake_pil_image.open = MagicMock(return_value=fake_img)
        fake_pil = _make_module("PIL")
        fake_pil.Image = fake_pil_image
        fake_pil_image_mod = _make_module("PIL.Image")
        fake_pil_image_mod.open = fake_pil_image.open

        with patch.dict(
            sys.modules,
            {"pytesseract": fake_pt, "PIL": fake_pil, "PIL.Image": fake_pil_image_mod},
        ):
            extractor = TesseractExtractor(config={"lang": "chi_sim", "psm": 6})
            result = extractor.extract(fake_path)

        fake_pt.image_to_string.assert_called_once_with(
            fake_img, lang="chi_sim", config="--psm 6"
        )
        assert result == "OCR result"

    def test_extract_uses_default_lang_and_psm(self, tmp_path: Path) -> None:
        from all2txt.backends.ocr import TesseractExtractor

        fake_path = tmp_path / "image.png"
        fake_path.touch()

        fake_img = MagicMock()

        fake_pt = _make_module("pytesseract")
        fake_pt.image_to_string = MagicMock(return_value="text")

        fake_pil_image = MagicMock()
        fake_pil_image.open = MagicMock(return_value=fake_img)
        fake_pil = _make_module("PIL")
        fake_pil.Image = fake_pil_image
        fake_pil_image_mod = _make_module("PIL.Image")
        fake_pil_image_mod.open = fake_pil_image.open

        with patch.dict(
            sys.modules,
            {"pytesseract": fake_pt, "PIL": fake_pil, "PIL.Image": fake_pil_image_mod},
        ):
            extractor = TesseractExtractor()
            extractor.extract(fake_path)

        fake_pt.image_to_string.assert_called_once_with(
            fake_img, lang="eng", config="--psm 3"
        )


# ===========================================================================
# EasyOCRExtractor
# ===========================================================================


class TestEasyOCRExtractor:
    def test_available_returns_false_when_easyocr_not_importable(self) -> None:
        from all2txt.backends.ocr import EasyOCRExtractor

        with patch.dict(sys.modules, {"easyocr": None}):
            assert EasyOCRExtractor().available() is False

    def test_available_returns_true_when_easyocr_importable(self) -> None:
        from all2txt.backends.ocr import EasyOCRExtractor

        fake_easyocr = _make_module("easyocr")
        with patch.dict(sys.modules, {"easyocr": fake_easyocr}):
            assert EasyOCRExtractor().available() is True

    def test_extract_uses_configured_langs(self, tmp_path: Path) -> None:
        from all2txt.backends.ocr import EasyOCRExtractor

        fake_path = tmp_path / "image.png"
        fake_path.touch()

        fake_reader_instance = MagicMock()
        fake_reader_instance.readtext.return_value = ["line one", "line two"]

        fake_easyocr = _make_module("easyocr")
        fake_easyocr.Reader = MagicMock(return_value=fake_reader_instance)

        with patch.dict(sys.modules, {"easyocr": fake_easyocr}):
            extractor = EasyOCRExtractor(config={"langs": ["en", "ch_sim"]})
            result = extractor.extract(fake_path)

        fake_easyocr.Reader.assert_called_once_with(["en", "ch_sim"])
        fake_reader_instance.readtext.assert_called_once_with(str(fake_path), detail=0)
        assert result == "line one\nline two"

    def test_extract_uses_default_langs(self, tmp_path: Path) -> None:
        from all2txt.backends.ocr import EasyOCRExtractor

        fake_path = tmp_path / "image.png"
        fake_path.touch()

        fake_reader_instance = MagicMock()
        fake_reader_instance.readtext.return_value = []

        fake_easyocr = _make_module("easyocr")
        fake_easyocr.Reader = MagicMock(return_value=fake_reader_instance)

        with patch.dict(sys.modules, {"easyocr": fake_easyocr}):
            extractor = EasyOCRExtractor()
            extractor.extract(fake_path)

        fake_easyocr.Reader.assert_called_once_with(["en"])


# ===========================================================================
# PaddleOCRExtractor
# ===========================================================================


class TestPaddleOCRExtractor:
    def test_available_returns_false_when_paddleocr_not_importable(self) -> None:
        from all2txt.backends.ocr import PaddleOCRExtractor

        with patch.dict(sys.modules, {"paddleocr": None}):
            assert PaddleOCRExtractor().available() is False

    def test_available_returns_true_when_paddleocr_importable(self) -> None:
        from all2txt.backends.ocr import PaddleOCRExtractor

        fake_paddleocr_mod = _make_module("paddleocr")
        fake_paddleocr_mod.PaddleOCR = MagicMock()
        with patch.dict(sys.modules, {"paddleocr": fake_paddleocr_mod}):
            assert PaddleOCRExtractor().available() is True

    def test_extract_uses_configured_lang_and_joins_lines(self, tmp_path: Path) -> None:
        from all2txt.backends.ocr import PaddleOCRExtractor

        fake_path = tmp_path / "image.png"
        fake_path.touch()

        # Each line in result: [bbox, (text, confidence)]
        fake_result = [
            [
                [None, ("Hello", 0.99)],
                [None, ("World", 0.95)],
            ]
        ]

        fake_ocr_instance = MagicMock()
        fake_ocr_instance.ocr.return_value = fake_result

        fake_paddleocr_mod = _make_module("paddleocr")
        fake_paddleocr_mod.PaddleOCR = MagicMock(return_value=fake_ocr_instance)

        with patch.dict(sys.modules, {"paddleocr": fake_paddleocr_mod}):
            extractor = PaddleOCRExtractor(config={"lang": "en"})
            result = extractor.extract(fake_path)

        fake_paddleocr_mod.PaddleOCR.assert_called_once_with(use_angle_cls=True, lang="en")
        fake_ocr_instance.ocr.assert_called_once_with(str(fake_path), cls=True)
        assert result == "Hello\nWorld"

    def test_extract_uses_default_lang(self, tmp_path: Path) -> None:
        from all2txt.backends.ocr import PaddleOCRExtractor

        fake_path = tmp_path / "image.png"
        fake_path.touch()

        fake_ocr_instance = MagicMock()
        fake_ocr_instance.ocr.return_value = [[]]

        fake_paddleocr_mod = _make_module("paddleocr")
        fake_paddleocr_mod.PaddleOCR = MagicMock(return_value=fake_ocr_instance)

        with patch.dict(sys.modules, {"paddleocr": fake_paddleocr_mod}):
            extractor = PaddleOCRExtractor()
            extractor.extract(fake_path)

        fake_paddleocr_mod.PaddleOCR.assert_called_once_with(use_angle_cls=True, lang="ch")


# ===========================================================================
# OpenAIVisionExtractor
# ===========================================================================


class TestOpenAIVisionExtractor:
    def test_available_returns_false_when_openai_not_importable(self) -> None:
        from all2txt.backends.openai_vision import OpenAIVisionExtractor

        with patch.dict(sys.modules, {"openai": None}):
            assert OpenAIVisionExtractor().available() is False

    def test_available_returns_true_when_openai_importable(self) -> None:
        from all2txt.backends.openai_vision import OpenAIVisionExtractor

        fake_openai = _make_module("openai")
        fake_openai.OpenAI = MagicMock()
        with patch.dict(sys.modules, {"openai": fake_openai}):
            assert OpenAIVisionExtractor().available() is True

    def test_extract_base64_encodes_and_sends_to_openai(self, tmp_path: Path) -> None:
        from all2txt.backends.openai_vision import OpenAIVisionExtractor

        fake_path = tmp_path / "photo.png"
        image_bytes = b"\x89PNG\r\n\x1a\n"
        fake_path.write_bytes(image_bytes)

        expected_b64 = base64.standard_b64encode(image_bytes).decode()

        mock_message = MagicMock()
        mock_message.content = "extracted text from image"
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client_instance = MagicMock()
        mock_client_instance.chat.completions.create.return_value = mock_response

        fake_openai = _make_module("openai")
        fake_openai.OpenAI = MagicMock(return_value=mock_client_instance)

        with patch.dict(sys.modules, {"openai": fake_openai}):
            extractor = OpenAIVisionExtractor()
            result = extractor.extract(fake_path)

        assert result == "extracted text from image"
        create_call = mock_client_instance.chat.completions.create.call_args
        messages = create_call[1]["messages"]
        image_url = messages[0]["content"][1]["image_url"]["url"]
        assert expected_b64 in image_url
        assert "image/png" in image_url

    def test_extract_uses_configured_model_and_prompt(self, tmp_path: Path) -> None:
        from all2txt.backends.openai_vision import OpenAIVisionExtractor

        fake_path = tmp_path / "photo.png"
        fake_path.write_bytes(b"data")

        mock_message = MagicMock()
        mock_message.content = "described"
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client_instance = MagicMock()
        mock_client_instance.chat.completions.create.return_value = mock_response

        fake_openai = _make_module("openai")
        fake_openai.OpenAI = MagicMock(return_value=mock_client_instance)

        with patch.dict(sys.modules, {"openai": fake_openai}):
            extractor = OpenAIVisionExtractor(
                config={"mode": "describe", "model": "gpt-4-turbo", "prompt": "Custom prompt"}
            )
            extractor.extract(fake_path)

        create_call = mock_client_instance.chat.completions.create.call_args
        assert create_call[1]["model"] == "gpt-4-turbo"
        messages = create_call[1]["messages"]
        text_part = messages[0]["content"][0]
        assert text_part["text"] == "Custom prompt"

    def test_extract_uses_describe_mode_default_prompt(self, tmp_path: Path) -> None:
        from all2txt.backends.openai_vision import (
            _DEFAULT_DESCRIBE_PROMPT,
            OpenAIVisionExtractor,
        )

        fake_path = tmp_path / "photo.png"
        fake_path.write_bytes(b"data")

        mock_message = MagicMock()
        mock_message.content = ""
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client_instance = MagicMock()
        mock_client_instance.chat.completions.create.return_value = mock_response

        fake_openai = _make_module("openai")
        fake_openai.OpenAI = MagicMock(return_value=mock_client_instance)

        with patch.dict(sys.modules, {"openai": fake_openai}):
            extractor = OpenAIVisionExtractor(config={"mode": "describe"})
            extractor.extract(fake_path)

        create_call = mock_client_instance.chat.completions.create.call_args
        messages = create_call[1]["messages"]
        text_part = messages[0]["content"][0]
        assert text_part["text"] == _DEFAULT_DESCRIBE_PROMPT


# ===========================================================================
# ASR backends
# ===========================================================================


class TestOpenAIWhisperExtractor:
    def test_available_returns_false_when_openai_missing(self) -> None:
        from all2txt.backends.asr import OpenAIWhisperExtractor

        with patch.dict(sys.modules, {"openai": None}):
            assert OpenAIWhisperExtractor().available() is False

    def test_available_returns_true_when_openai_present(self) -> None:
        from all2txt.backends.asr import OpenAIWhisperExtractor

        fake_openai = _make_module("openai")
        fake_openai.OpenAI = MagicMock()
        with patch.dict(sys.modules, {"openai": fake_openai}):
            assert OpenAIWhisperExtractor().available() is True

    def test_extract_audio_file_calls_api(self, tmp_path: Path) -> None:
        from all2txt.backends.asr import OpenAIWhisperExtractor

        fake_path = tmp_path / "audio.mp3"
        fake_path.write_bytes(b"audio data")

        mock_result = MagicMock()
        mock_result.text = "transcribed text"

        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = mock_result

        fake_openai = _make_module("openai")
        fake_openai.OpenAI = MagicMock(return_value=mock_client)

        with (
            patch.dict(sys.modules, {"openai": fake_openai}),
            patch("all2txt.backends.asr._is_video", return_value=False),
        ):
            extractor = OpenAIWhisperExtractor()
            result = extractor.extract(fake_path)

        assert result == "transcribed text"
        mock_client.audio.transcriptions.create.assert_called_once()
        call_kwargs = mock_client.audio.transcriptions.create.call_args[1]
        assert call_kwargs["model"] == "whisper-1"
        assert call_kwargs["response_format"] == "text"

    def test_extract_video_file_extracts_audio_first(self, tmp_path: Path) -> None:
        from all2txt.backends.asr import OpenAIWhisperExtractor

        fake_path = tmp_path / "video.mp4"
        fake_path.write_bytes(b"video data")
        fake_audio_path = tmp_path / "audio.wav"
        fake_audio_path.write_bytes(b"audio data")

        mock_result = "transcribed"  # str response

        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = mock_result

        fake_openai = _make_module("openai")
        fake_openai.OpenAI = MagicMock(return_value=mock_client)

        with (
            patch.dict(sys.modules, {"openai": fake_openai}),
            patch("all2txt.backends.asr._is_video", return_value=True),
            patch(
                "all2txt.backends.asr.extract_audio", return_value=fake_audio_path
            ) as mock_extract,
            patch("os.unlink") as mock_unlink,
        ):
            extractor = OpenAIWhisperExtractor()
            result = extractor.extract(fake_path)

        mock_extract.assert_called_once_with(fake_path)
        mock_unlink.assert_called_once_with(fake_audio_path)
        assert result == "transcribed"

    def test_extract_passes_language_when_configured(self, tmp_path: Path) -> None:
        from all2txt.backends.asr import OpenAIWhisperExtractor

        fake_path = tmp_path / "audio.mp3"
        fake_path.write_bytes(b"data")

        mock_result = MagicMock()
        mock_result.text = "text"
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = mock_result

        fake_openai = _make_module("openai")
        fake_openai.OpenAI = MagicMock(return_value=mock_client)

        with (
            patch.dict(sys.modules, {"openai": fake_openai}),
            patch("all2txt.backends.asr._is_video", return_value=False),
        ):
            extractor = OpenAIWhisperExtractor(config={"language": "zh"})
            extractor.extract(fake_path)

        call_kwargs = mock_client.audio.transcriptions.create.call_args[1]
        assert call_kwargs["language"] == "zh"


class TestFasterWhisperExtractor:
    def test_available_returns_false_when_faster_whisper_missing(self) -> None:
        from all2txt.backends.asr import FasterWhisperExtractor

        with patch.dict(sys.modules, {"faster_whisper": None}):
            assert FasterWhisperExtractor().available() is False

    def test_available_returns_true_when_faster_whisper_present(self) -> None:
        from all2txt.backends.asr import FasterWhisperExtractor

        fake_fw = _make_module("faster_whisper")
        fake_fw.WhisperModel = MagicMock()
        with patch.dict(sys.modules, {"faster_whisper": fake_fw}):
            assert FasterWhisperExtractor().available() is True

    def test_extract_audio_joins_segments(self, tmp_path: Path) -> None:
        from all2txt.backends.asr import FasterWhisperExtractor

        fake_path = tmp_path / "audio.wav"
        fake_path.write_bytes(b"data")

        seg1 = MagicMock()
        seg1.text = "  Hello  "
        seg2 = MagicMock()
        seg2.text = " world  "

        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([seg1, seg2], MagicMock())

        fake_fw = _make_module("faster_whisper")
        fake_fw.WhisperModel = MagicMock(return_value=mock_model)

        with (
            patch.dict(sys.modules, {"faster_whisper": fake_fw}),
            patch("all2txt.backends.asr._is_video", return_value=False),
        ):
            extractor = FasterWhisperExtractor(config={"model": "small", "device": "cuda"})
            result = extractor.extract(fake_path)

        fake_fw.WhisperModel.assert_called_once_with("small", device="cuda")
        assert result == "Hello world"

    def test_extract_video_extracts_audio_first(self, tmp_path: Path) -> None:
        from all2txt.backends.asr import FasterWhisperExtractor

        fake_path = tmp_path / "video.mkv"
        fake_path.write_bytes(b"data")
        fake_audio_path = tmp_path / "tmp.wav"
        fake_audio_path.write_bytes(b"audio")

        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([], MagicMock())

        fake_fw = _make_module("faster_whisper")
        fake_fw.WhisperModel = MagicMock(return_value=mock_model)

        with (
            patch.dict(sys.modules, {"faster_whisper": fake_fw}),
            patch("all2txt.backends.asr._is_video", return_value=True),
            patch(
                "all2txt.backends.asr.extract_audio", return_value=fake_audio_path
            ) as mock_extract,
            patch("os.unlink") as mock_unlink,
        ):
            extractor = FasterWhisperExtractor()
            extractor.extract(fake_path)

        mock_extract.assert_called_once_with(fake_path)
        mock_unlink.assert_called_once_with(fake_audio_path)


class TestWhisperLocalExtractor:
    def test_available_returns_false_when_whisper_missing(self) -> None:
        from all2txt.backends.asr import WhisperLocalExtractor

        with patch.dict(sys.modules, {"whisper": None}):
            assert WhisperLocalExtractor().available() is False

    def test_available_returns_false_when_ffmpeg_missing(self) -> None:
        from all2txt.backends.asr import WhisperLocalExtractor

        fake_whisper = _make_module("whisper")
        with (
            patch.dict(sys.modules, {"whisper": fake_whisper}),
            patch("shutil.which", return_value=None),
        ):
            assert WhisperLocalExtractor().available() is False

    def test_available_returns_true_when_both_present(self) -> None:
        from all2txt.backends.asr import WhisperLocalExtractor

        fake_whisper = _make_module("whisper")
        with (
            patch.dict(sys.modules, {"whisper": fake_whisper}),
            patch("shutil.which", return_value="/usr/bin/ffmpeg"),
        ):
            assert WhisperLocalExtractor().available() is True

    def test_extract_audio_transcribes_and_returns_text(self, tmp_path: Path) -> None:
        from all2txt.backends.asr import WhisperLocalExtractor

        fake_path = tmp_path / "audio.flac"
        fake_path.write_bytes(b"data")

        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": "transcription result"}

        fake_whisper = _make_module("whisper")
        fake_whisper.load_model = MagicMock(return_value=mock_model)

        with (
            patch.dict(sys.modules, {"whisper": fake_whisper}),
            patch("all2txt.backends.asr._is_video", return_value=False),
        ):
            extractor = WhisperLocalExtractor(config={"model": "small"})
            result = extractor.extract(fake_path)

        fake_whisper.load_model.assert_called_once_with("small")
        mock_model.transcribe.assert_called_once_with(str(fake_path))
        assert result == "transcription result"

    def test_extract_video_extracts_audio_first(self, tmp_path: Path) -> None:
        from all2txt.backends.asr import WhisperLocalExtractor

        fake_path = tmp_path / "video.mp4"
        fake_path.write_bytes(b"data")
        fake_audio_path = tmp_path / "tmp.wav"
        fake_audio_path.write_bytes(b"audio")

        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": "video transcription"}

        fake_whisper = _make_module("whisper")
        fake_whisper.load_model = MagicMock(return_value=mock_model)

        with (
            patch.dict(sys.modules, {"whisper": fake_whisper}),
            patch("all2txt.backends.asr._is_video", return_value=True),
            patch(
                "all2txt.backends.asr.extract_audio", return_value=fake_audio_path
            ) as mock_extract,
            patch("os.unlink") as mock_unlink,
        ):
            extractor = WhisperLocalExtractor()
            result = extractor.extract(fake_path)

        mock_extract.assert_called_once_with(fake_path)
        mock_model.transcribe.assert_called_once_with(str(fake_audio_path))
        mock_unlink.assert_called_once_with(fake_audio_path)
        assert result == "video transcription"

    def test_extract_passes_language_kwarg(self, tmp_path: Path) -> None:
        from all2txt.backends.asr import WhisperLocalExtractor

        fake_path = tmp_path / "audio.wav"
        fake_path.write_bytes(b"data")

        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": "text"}

        fake_whisper = _make_module("whisper")
        fake_whisper.load_model = MagicMock(return_value=mock_model)

        with (
            patch.dict(sys.modules, {"whisper": fake_whisper}),
            patch("all2txt.backends.asr._is_video", return_value=False),
        ):
            extractor = WhisperLocalExtractor(config={"language": "fr"})
            extractor.extract(fake_path)

        mock_model.transcribe.assert_called_once_with(str(fake_path), language="fr")


# ===========================================================================
# _util.extract_audio
# ===========================================================================


class TestExtractAudio:
    def test_extract_audio_calls_ffmpeg_with_correct_args(self, tmp_path: Path) -> None:
        from all2txt.backends._util import extract_audio

        fake_video = tmp_path / "video.mp4"
        fake_video.write_bytes(b"data")

        fake_fd = 5
        fake_tmp_wav = str(tmp_path / "tmp_audio.wav")

        with (
            patch("tempfile.mkstemp", return_value=(fake_fd, fake_tmp_wav)),
            patch("os.close") as mock_close,
            patch("subprocess.run") as mock_run,
        ):
            result = extract_audio(fake_video)

        mock_close.assert_called_once_with(fake_fd)
        mock_run.assert_called_once_with(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(fake_video),
                "-vn",
                "-ar",
                "16000",
                "-ac",
                "1",
                "-f",
                "wav",
                fake_tmp_wav,
            ],
            capture_output=True,
            check=True,
        )
        assert result == Path(fake_tmp_wav)

    def test_extract_audio_cleans_up_temp_file_on_failure(self, tmp_path: Path) -> None:
        from all2txt.backends._util import extract_audio

        fake_video = tmp_path / "video.mp4"
        fake_video.write_bytes(b"data")

        fake_fd = 5
        fake_tmp_wav = str(tmp_path / "tmp_audio.wav")

        with (
            patch("tempfile.mkstemp", return_value=(fake_fd, fake_tmp_wav)),
            patch("os.close"),
            patch("subprocess.run", side_effect=RuntimeError("ffmpeg failed")),
            patch("os.unlink") as mock_unlink,
        ):
            with pytest.raises(RuntimeError, match="ffmpeg failed"):
                extract_audio(fake_video)

        mock_unlink.assert_called_once_with(fake_tmp_wav)
