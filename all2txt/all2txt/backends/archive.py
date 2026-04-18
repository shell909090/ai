import bz2
import gzip
import lzma
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from ..core.base import Extractor
from ..core.registry import registry

_DEFAULT_MAX_BYTES = 100 * 1024 * 1024

_ARCHIVE_MIMES = (
    "application/zip",
    "application/x-tar",
    "application/gzip",
    "application/x-bzip2",
    "application/x-xz",
    "application/x-lzma",
)

_SINGLE_COMPRESSED: dict[str, Any] = {
    "application/gzip": gzip.open,
    "application/x-bzip2": bz2.open,
    "application/x-xz": lzma.open,
    "application/x-lzma": lzma.open,
}

_ALL_ARCHIVE_BACKEND_NAMES = (
    "archive_recurse",
    "7zip_recurse",
    "rar_recurse",
)


@registry.register(*_ARCHIVE_MIMES)
class ArchiveExtractor(Extractor):
    """Recursively extract text from zip, tar.*, and single-file compressed files."""

    name = "archive_recurse"
    priority = 10

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._max_bytes: int = int(self._cfg.get("max_bytes", _DEFAULT_MAX_BYTES))

    def available(self) -> bool:
        """Return True only when explicitly enabled in config."""
        return bool(self._cfg.get("enabled", False))

    def extract(self, path: Path) -> str:
        """Detect archive format and dispatch to the appropriate extraction path."""
        from ..core.registry import registry as _registry

        if zipfile.is_zipfile(path):
            return self._extract_zip(path, _registry)
        if tarfile.is_tarfile(path):
            return self._extract_tar(path, _registry)
        open_fn = _SINGLE_COMPRESSED.get(self._cfg.get("_mime", ""))
        if open_fn:
            return self._extract_single(path, _registry, open_fn)
        raise RuntimeError(f"Unrecognised archive format: {path}")

    def _extract_zip(self, path: Path, reg: Any) -> str:
        """Extract a ZIP archive and return combined member text."""
        with zipfile.ZipFile(path) as zf:
            infos = zf.infolist()
            total = sum(i.file_size for i in infos)
            if total > self._max_bytes:
                raise RuntimeError(
                    f"Archive uncompressed size {total} exceeds max_bytes {self._max_bytes}"
                )
            tmpdir = tempfile.mkdtemp()
            try:
                zf.extractall(tmpdir)
                parts: list[str] = []
                for info in infos:
                    if info.is_dir():
                        continue
                    member_path = Path(tmpdir) / info.filename
                    parts.append(self._extract_member(info.filename, member_path, reg))
                return "\n\n".join(parts)
            finally:
                shutil.rmtree(tmpdir)

    def _extract_tar(self, path: Path, reg: Any) -> str:
        """Extract a TAR archive (including gz/bz2/xz variants) and return combined member text."""
        with tarfile.open(path, mode="r:*") as tf:
            members = tf.getmembers()
            total = sum(m.size for m in members)
            if total > self._max_bytes:
                raise RuntimeError(
                    f"Archive uncompressed size {total} exceeds max_bytes {self._max_bytes}"
                )
            tmpdir = tempfile.mkdtemp()
            try:
                tf.extractall(tmpdir, filter="data")
                parts: list[str] = []
                for member in members:
                    if not member.isfile():
                        continue
                    member_path = Path(tmpdir) / member.name
                    parts.append(self._extract_member(member.name, member_path, reg))
                return "\n\n".join(parts)
            finally:
                shutil.rmtree(tmpdir)

    def _extract_single(self, path: Path, reg: Any, open_fn: Any) -> str:
        """Decompress a single-file archive, then extract text from the inner file."""
        stem = path.stem
        tmpdir = tempfile.mkdtemp()
        try:
            inner_path = Path(tmpdir) / stem
            total = 0
            with open_fn(path, "rb") as src, inner_path.open("wb") as dst:
                for chunk in iter(lambda: src.read(65536), b""):
                    total += len(chunk)
                    if total > self._max_bytes:
                        raise RuntimeError(f"Decompressed size exceeds max_bytes {self._max_bytes}")
                    dst.write(chunk)
            return self._extract_member(stem, inner_path, reg)
        finally:
            shutil.rmtree(tmpdir)

    def _extract_member(self, internal_name: str, member_path: Path, reg: Any) -> str:
        """Extract one member; return header + text, or header + error on failure."""
        try:
            text = reg.extract(member_path)
            return f"=== {internal_name} ===\n{text}"
        except Exception as exc:
            return f"=== {internal_name} === (error: {exc})"


@registry.register("application/x-7z-compressed")
class SevenZipExtractor(Extractor):
    """Recursively extract text from 7-Zip archives via py7zr."""

    name = "7zip_recurse"
    priority = 10

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._max_bytes: int = int(self._cfg.get("max_bytes", _DEFAULT_MAX_BYTES))

    def available(self) -> bool:
        """Return True only when enabled and py7zr is installed."""
        if not self._cfg.get("enabled", False):
            return False
        try:
            import py7zr  # noqa: F401

            return True
        except ImportError:
            return False

    def extract(self, path: Path) -> str:
        """Extract a 7-Zip archive and recursively process each member."""
        import py7zr

        from ..core.registry import registry as _registry

        with py7zr.SevenZipFile(path, mode="r") as zf:
            infos = zf.list()
            total = sum(f.uncompressed for f in infos if not f.is_directory)
            if total > self._max_bytes:
                raise RuntimeError(
                    f"Archive uncompressed size {total} exceeds max_bytes {self._max_bytes}"
                )
            tmpdir = tempfile.mkdtemp()
            try:
                zf.extractall(path=tmpdir)
                parts: list[str] = []
                for info in infos:
                    if info.is_directory:
                        continue
                    member_path = Path(tmpdir) / info.filename
                    parts.append(self._extract_member(info.filename, member_path, _registry))
                return "\n\n".join(parts)
            finally:
                shutil.rmtree(tmpdir)

    def _extract_member(self, internal_name: str, member_path: Path, reg: Any) -> str:
        """Extract one member; return header + text, or header + error on failure."""
        try:
            text = reg.extract(member_path)
            return f"=== {internal_name} ===\n{text}"
        except Exception as exc:
            return f"=== {internal_name} === (error: {exc})"


@registry.register("application/x-rar", "application/vnd.rar", "application/x-rar-compressed")
class RarExtractor(Extractor):
    """Recursively extract text from RAR archives via rarfile."""

    name = "rar_recurse"
    priority = 10

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._max_bytes: int = int(self._cfg.get("max_bytes", _DEFAULT_MAX_BYTES))

    def available(self) -> bool:
        """Return True only when enabled and rarfile is installed."""
        if not self._cfg.get("enabled", False):
            return False
        try:
            import rarfile  # noqa: F401

            return True
        except ImportError:
            return False

    def extract(self, path: Path) -> str:
        """Extract a RAR archive and recursively process each member."""
        import rarfile

        from ..core.registry import registry as _registry

        with rarfile.RarFile(path) as rf:
            infos = rf.infolist()
            total = sum(i.file_size for i in infos if not i.is_dir())
            if total > self._max_bytes:
                raise RuntimeError(
                    f"Archive uncompressed size {total} exceeds max_bytes {self._max_bytes}"
                )
            tmpdir = tempfile.mkdtemp()
            try:
                rf.extractall(tmpdir)
                parts: list[str] = []
                for info in infos:
                    if info.is_dir():
                        continue
                    member_path = Path(tmpdir) / info.filename
                    parts.append(self._extract_member(info.filename, member_path, _registry))
                return "\n\n".join(parts)
            finally:
                shutil.rmtree(tmpdir)

    def _extract_member(self, internal_name: str, member_path: Path, reg: Any) -> str:
        """Extract one member; return header + text, or header + error on failure."""
        try:
            text = reg.extract(member_path)
            return f"=== {internal_name} ===\n{text}"
        except Exception as exc:
            return f"=== {internal_name} === (error: {exc})"
