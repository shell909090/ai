"""LanceDB interface: files (metadata) and chunks (vectors) tables."""

import logging
from pathlib import Path

import pyarrow as pa

logger = logging.getLogger(__name__)

FILES_TABLE = "files"
CHUNKS_TABLE = "chunks"

_FILES_SCHEMA = pa.schema([
    pa.field("path", pa.utf8()),
    pa.field("size", pa.int64()),
    pa.field("mtime", pa.float64()),
    pa.field("file_hash", pa.utf8()),
])


def _chunks_schema(dim: int) -> pa.Schema:
    return pa.schema([
        pa.field("file_hash", pa.utf8()),
        pa.field("chunk_index", pa.int32()),
        pa.field("start", pa.int32()),
        pa.field("end", pa.int32()),
        pa.field("content", pa.utf8()),
        pa.field("vector", pa.list_(pa.float32(), dim)),
    ])


class VectorDB:
    """Manages LanceDB files and chunks tables."""

    def __init__(self, index_path: Path) -> None:
        import lancedb  # deferred: avoid slow import at CLI startup

        index_path.mkdir(parents=True, exist_ok=True)
        self._db = lancedb.connect(str(index_path))

    # ------------------------------------------------------------------ tables

    def init_tables(self, dim: int) -> None:
        """Create files and chunks tables if they do not exist."""
        raise NotImplementedError

    def drop_tables(self) -> None:
        """Drop both tables (used in tests or force-rebuild)."""
        raise NotImplementedError

    def tables_exist(self) -> bool:
        """Return True if both files and chunks tables exist."""
        raise NotImplementedError

    # ------------------------------------------------------------------ files

    def get_file_meta(self, path: str) -> dict | None:
        """Return stored metadata for path, or None if not indexed."""
        raise NotImplementedError

    def upsert_file_meta(self, path: str, size: int, mtime: float, file_hash: str) -> None:
        """Insert or overwrite file metadata record."""
        raise NotImplementedError

    def delete_file_meta(self, path: str) -> None:
        """Remove file metadata record."""
        raise NotImplementedError

    def list_indexed_paths(self) -> list[str]:
        """Return all paths currently in files table."""
        raise NotImplementedError

    def get_paths_by_hash(self, file_hash: str) -> list[str]:
        """Return all file paths that share the given content hash."""
        raise NotImplementedError

    # ------------------------------------------------------------------ chunks

    def hash_has_chunks(self, file_hash: str) -> bool:
        """Return True if at least one chunk exists for this file_hash."""
        raise NotImplementedError

    def add_chunks(self, records: list[dict]) -> None:
        """Bulk-insert chunk records (file_hash/chunk_index/start/end/content/vector)."""
        raise NotImplementedError

    def delete_chunks_by_hash(self, file_hash: str) -> None:
        """Delete all chunks for this file_hash."""
        raise NotImplementedError

    def query(self, vector: list[float], top_k: int) -> list[dict]:
        """Cosine ANN search; returns dicts with file_hash/chunk_index/start/end/content/_distance."""
        raise NotImplementedError
