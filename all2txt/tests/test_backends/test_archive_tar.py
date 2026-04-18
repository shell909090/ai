"""Tests for ArchiveExtractor: TAR extraction and single-file compressed formats."""

from __future__ import annotations

import bz2
import gzip
import io
import lzma
import tarfile
from pathlib import Path

import pytest

# Trigger backend registration so PlainTextExtractor is available for text/plain.
import all2txt.backends as _  # noqa: F401


# ===========================================================================
# ArchiveExtractor – plain TAR extraction
# ===========================================================================


class TestArchiveExtractorExtractTar:
    def test_extract_tar_single_txt_member(self, tmp_path: Path) -> None:
        """Plain TAR archive with one .txt file produces correct header and content."""
        from all2txt.backends.archive import ArchiveExtractor

        content = b"Hello from tar!"
        tar_path = tmp_path / "test.tar"
        with tarfile.open(tar_path, "w") as tf:
            info = tarfile.TarInfo(name="hello.txt")
            info.size = len(content)
            tf.addfile(info, io.BytesIO(content))

        extractor = ArchiveExtractor(config={"enabled": True})
        result = extractor.extract(tar_path)

        assert "=== hello.txt ===" in result
        assert "Hello from tar!" in result

    def test_extract_tar_header_format(self, tmp_path: Path) -> None:
        """TAR output contains '=== filename ===\\n{content}' format."""
        from all2txt.backends.archive import ArchiveExtractor

        body = b"tar body text"
        tar_path = tmp_path / "fmt.tar"
        with tarfile.open(tar_path, "w") as tf:
            info = tarfile.TarInfo(name="doc.txt")
            info.size = len(body)
            tf.addfile(info, io.BytesIO(body))

        extractor = ArchiveExtractor(config={"enabled": True})
        result = extractor.extract(tar_path)

        assert result.startswith("=== doc.txt ===\n")
        assert "tar body text" in result


# ===========================================================================
# ArchiveExtractor – TAR+GZ extraction
# ===========================================================================


class TestArchiveExtractorExtractTarGz:
    def test_extract_tar_gz_single_txt_member(self, tmp_path: Path) -> None:
        """.tar.gz archive with one .txt file produces correct output."""
        from all2txt.backends.archive import ArchiveExtractor

        content = b"Hello from tar.gz!"
        tar_gz_path = tmp_path / "test.tar.gz"
        with tarfile.open(tar_gz_path, "w:gz") as tf:
            info = tarfile.TarInfo(name="hello.txt")
            info.size = len(content)
            tf.addfile(info, io.BytesIO(content))

        extractor = ArchiveExtractor(config={"enabled": True})
        result = extractor.extract(tar_gz_path)

        assert "=== hello.txt ===" in result
        assert "Hello from tar.gz!" in result


# ===========================================================================
# ArchiveExtractor – single-file compressed formats
# ===========================================================================


class TestArchiveExtractorSingleFileCompressed:
    def test_extract_single_gz(self, tmp_path: Path) -> None:
        """A plain .txt.gz file (not a tarball) is decompressed and its text extracted."""
        from all2txt.backends.archive import ArchiveExtractor

        content = b"Hello from gzip!"
        gz_path = tmp_path / "hello.txt.gz"
        with gzip.open(gz_path, "wb") as f:
            f.write(content)

        extractor = ArchiveExtractor(config={"enabled": True, "_mime": "application/gzip"})
        result = extractor.extract(gz_path)

        assert "=== hello.txt ===" in result
        assert "Hello from gzip!" in result

    def test_extract_single_bz2(self, tmp_path: Path) -> None:
        """A plain .txt.bz2 file is decompressed and its text extracted."""
        from all2txt.backends.archive import ArchiveExtractor

        content = b"Hello from bzip2!"
        bz2_path = tmp_path / "hello.txt.bz2"
        with bz2.open(bz2_path, "wb") as f:
            f.write(content)

        extractor = ArchiveExtractor(config={"enabled": True, "_mime": "application/x-bzip2"})
        result = extractor.extract(bz2_path)

        assert "=== hello.txt ===" in result
        assert "Hello from bzip2!" in result

    def test_extract_single_xz(self, tmp_path: Path) -> None:
        """A plain .txt.xz file is decompressed and its text extracted."""
        from all2txt.backends.archive import ArchiveExtractor

        content = b"Hello from xz!"
        xz_path = tmp_path / "hello.txt.xz"
        with lzma.open(xz_path, "wb") as f:
            f.write(content)

        extractor = ArchiveExtractor(config={"enabled": True, "_mime": "application/x-xz"})
        result = extractor.extract(xz_path)

        assert "=== hello.txt ===" in result
        assert "Hello from xz!" in result

    def test_single_gz_bomb_protection(self, tmp_path: Path) -> None:
        """Decompression aborts when output exceeds max_bytes."""
        from all2txt.backends.archive import ArchiveExtractor

        gz_path = tmp_path / "big.txt.gz"
        with gzip.open(gz_path, "wb") as f:
            f.write(b"X" * 200)

        extractor = ArchiveExtractor(
            config={"enabled": True, "_mime": "application/gzip", "max_bytes": 100}
        )
        with pytest.raises(RuntimeError, match="max_bytes"):
            extractor.extract(gz_path)
