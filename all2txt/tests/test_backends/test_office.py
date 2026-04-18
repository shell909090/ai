"""Tests for office-document extraction backends."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.test_backends._helpers import _make_module

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
                "txt:Text (encoded):UTF8,LF,,,,0",
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
# NativeXlsxExtractor closes workbook on exception (R009)
# ===========================================================================


class TestNativeXlsxExtractorClosesOnException:
    def test_workbook_closed_even_when_extract_raises(self, tmp_path: Path) -> None:
        from all2txt.backends.native_office import NativeXlsxExtractor

        fake_path = tmp_path / "bad.xlsx"
        fake_path.touch()

        wb_mock = MagicMock()
        ws_mock = MagicMock()
        ws_mock.iter_rows.side_effect = RuntimeError("corrupt xlsx")
        wb_mock.worksheets = [ws_mock]

        fake_openpyxl = _make_module("openpyxl")
        fake_openpyxl.load_workbook = MagicMock(return_value=wb_mock)

        with patch.dict(sys.modules, {"openpyxl": fake_openpyxl}):
            extractor = NativeXlsxExtractor()
            with pytest.raises(RuntimeError, match="corrupt xlsx"):
                extractor.extract(fake_path)

        wb_mock.close.assert_called_once()
