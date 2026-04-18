"""Tests for ArchiveExtractor: availability, ZIP extraction, ZIP bomb protection, failures."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

# Trigger backend registration so PlainTextExtractor is available for text/plain.
import all2txt.backends as _  # noqa: F401

# ===========================================================================
# ArchiveExtractor – availability
# ===========================================================================


class TestArchiveExtractorAvailable:
    def test_available_disabled_by_default(self) -> None:
        """available() returns False when 'enabled' key is absent from config."""
        from all2txt.backends.archive import ArchiveExtractor

        extractor = ArchiveExtractor()
        assert extractor.available() is False

    def test_available_false_when_enabled_false(self) -> None:
        """available() returns False when enabled is explicitly False."""
        from all2txt.backends.archive import ArchiveExtractor

        extractor = ArchiveExtractor(config={"enabled": False})
        assert extractor.available() is False

    def test_available_true_when_enabled(self) -> None:
        """available() returns True when enabled is set to True."""
        from all2txt.backends.archive import ArchiveExtractor

        extractor = ArchiveExtractor(config={"enabled": True})
        assert extractor.available() is True


# ===========================================================================
# ArchiveExtractor – ZIP extraction
# ===========================================================================


class TestArchiveExtractorExtractZip:
    def test_extract_zip_single_txt_member(self, tmp_path: Path) -> None:
        """ZIP archive with one .txt file produces correct header and content."""
        from all2txt.backends.archive import ArchiveExtractor

        content = "Hello from zip!"
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("hello.txt", content)

        extractor = ArchiveExtractor(config={"enabled": True})
        result = extractor.extract(zip_path)

        assert "=== hello.txt ===" in result
        assert content in result

    def test_extract_zip_header_format(self, tmp_path: Path) -> None:
        """Output contains '=== filename ===\\n{content}' format."""
        from all2txt.backends.archive import ArchiveExtractor

        zip_path = tmp_path / "fmt.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("readme.txt", "line one\nline two")

        extractor = ArchiveExtractor(config={"enabled": True})
        result = extractor.extract(zip_path)

        assert result.startswith("=== readme.txt ===\n")
        assert "line one\nline two" in result

    def test_extract_zip_multiple_members_separated_by_blank_line(self, tmp_path: Path) -> None:
        """Multiple members in a ZIP are separated by a blank line (\\n\\n)."""
        from all2txt.backends.archive import ArchiveExtractor

        zip_path = tmp_path / "multi.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("a.txt", "AAA")
            zf.writestr("b.txt", "BBB")

        extractor = ArchiveExtractor(config={"enabled": True})
        result = extractor.extract(zip_path)

        assert "=== a.txt ===" in result
        assert "=== b.txt ===" in result
        assert "\n\n" in result

    def test_extract_zip_skips_directory_entries(self, tmp_path: Path) -> None:
        """Directory entries inside a ZIP must not produce output sections."""
        from all2txt.backends.archive import ArchiveExtractor

        zip_path = tmp_path / "withdir.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            # Add a directory entry explicitly
            zf.mkdir("subdir")
            zf.writestr("subdir/file.txt", "nested")

        extractor = ArchiveExtractor(config={"enabled": True})
        result = extractor.extract(zip_path)

        # Only the file entry should appear; "subdir/" directory entry should be absent
        assert "=== subdir/file.txt ===" in result
        # There should be exactly one section header
        assert result.count("===") == 2  # one opening and one closing marker in "=== x ==="


# ===========================================================================
# ArchiveExtractor – ZIP bomb protection
# ===========================================================================


class TestArchiveExtractorZipBombProtection:
    def test_zip_bomb_raises_runtime_error(self, tmp_path: Path) -> None:
        """RuntimeError is raised when total uncompressed size exceeds max_bytes."""
        from all2txt.backends.archive import ArchiveExtractor

        # Write a real small file but set max_bytes=1 so any content triggers the limit.
        zip_path = tmp_path / "bomb.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("small.txt", "x")  # file_size = 1 byte

        # max_bytes=0 forces the check to trigger even for a 1-byte file
        extractor = ArchiveExtractor(config={"enabled": True, "max_bytes": 0})
        with pytest.raises(RuntimeError, match="max_bytes"):
            extractor.extract(zip_path)

    def test_zip_bomb_uses_zipinfo_file_size(self, tmp_path: Path) -> None:
        """The size check reads ZipInfo.file_size, not the compressed size."""
        from all2txt.backends.archive import ArchiveExtractor

        zip_path = tmp_path / "big.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            # Write compressible content; uncompressed size is 1000 bytes
            zf.writestr("data.txt", "A" * 1000)

        # Allow only 999 bytes → should raise
        extractor = ArchiveExtractor(config={"enabled": True, "max_bytes": 999})
        with pytest.raises(RuntimeError):
            extractor.extract(zip_path)

        # Allow exactly 1000 bytes → should succeed
        extractor_ok = ArchiveExtractor(config={"enabled": True, "max_bytes": 1000})
        result = extractor_ok.extract(zip_path)
        assert "=== data.txt ===" in result

    def test_tar_bomb_raises_runtime_error(self, tmp_path: Path) -> None:
        """RuntimeError is raised for TAR archives exceeding max_bytes."""
        import io
        import tarfile

        from all2txt.backends.archive import ArchiveExtractor

        content = b"X" * 100
        tar_path = tmp_path / "bomb.tar"
        with tarfile.open(tar_path, "w") as tf:
            info = tarfile.TarInfo(name="big.txt")
            info.size = len(content)
            tf.addfile(info, io.BytesIO(content))

        extractor = ArchiveExtractor(config={"enabled": True, "max_bytes": 99})
        with pytest.raises(RuntimeError, match="max_bytes"):
            extractor.extract(tar_path)


# ===========================================================================
# ArchiveExtractor – member failure continues
# ===========================================================================


class TestArchiveExtractorMemberFailureContinues:
    # PNG magic bytes produce application/octet-stream via file(1); that MIME
    # has no registered backend, so registry.extract() raises RuntimeError,
    # which ArchiveExtractor must catch and record as an error line.
    _UNHANDLED_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

    def test_unknown_mime_produces_error_record_not_exception(self, tmp_path: Path) -> None:
        """A member detected as application/octet-stream records an error and does not raise."""
        from all2txt.backends.archive import ArchiveExtractor

        zip_path = tmp_path / "mixed.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            # PNG magic → file(1) reports application/octet-stream → no backend
            zf.writestr("binary.xyz", self._UNHANDLED_BYTES)

        extractor = ArchiveExtractor(config={"enabled": True})
        result = extractor.extract(zip_path)

        assert "=== binary.xyz ===" in result
        assert "error:" in result

    def test_failure_in_one_member_does_not_skip_others(self, tmp_path: Path) -> None:
        """When one member fails, remaining members are still processed."""
        from all2txt.backends.archive import ArchiveExtractor

        zip_path = tmp_path / "partial.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            # First member will fail (no backend for octet-stream)
            zf.writestr("bad.xyz", self._UNHANDLED_BYTES)
            # Second member should still be extracted
            zf.writestr("good.txt", "extractable text")

        extractor = ArchiveExtractor(config={"enabled": True})
        result = extractor.extract(zip_path)

        assert "=== bad.xyz ===" in result
        assert "error:" in result
        assert "=== good.txt ===" in result
        assert "extractable text" in result
