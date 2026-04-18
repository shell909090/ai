"""LanceDB interface: files (metadata), chunks (vectors), and meta (key-value) tables."""

import logging
from pathlib import Path

import pyarrow as pa

logger = logging.getLogger(__name__)

FILES_TABLE = "files"
CHUNKS_TABLE = "chunks"
META_TABLE = "meta"

_FILES_SCHEMA = pa.schema(
    [
        pa.field("path", pa.utf8()),
        pa.field("size", pa.int64()),
        pa.field("mtime", pa.float64()),
        pa.field("file_hash", pa.utf8()),
    ]
)

_META_SCHEMA = pa.schema(
    [
        pa.field("key", pa.utf8()),
        pa.field("value", pa.utf8()),
    ]
)


def _chunks_schema(dim: int) -> pa.Schema:
    return pa.schema(
        [
            pa.field("file_hash", pa.utf8()),
            pa.field("chunk_index", pa.int32()),
            pa.field("start", pa.int32()),
            pa.field("end", pa.int32()),
            pa.field("content", pa.utf8()),
            pa.field("vector", pa.list_(pa.float32(), dim)),
        ]
    )


class VectorDB:
    """Manages LanceDB files, chunks, and meta tables."""

    def __init__(self, index_path: Path) -> None:
        import lancedb  # deferred: avoid slow import at CLI startup

        index_path.mkdir(parents=True, exist_ok=True)
        self._db = lancedb.connect(str(index_path))

    # ------------------------------------------------------------------ tables

    def _table_names(self) -> set[str]:
        return set(self._db.list_tables().tables)

    def init_tables(self, dim: int) -> None:
        """Create files, chunks, and meta tables if they do not exist."""
        existing = self._table_names()
        if FILES_TABLE not in existing:
            self._db.create_table(FILES_TABLE, schema=_FILES_SCHEMA)
        if CHUNKS_TABLE not in existing:
            self._db.create_table(CHUNKS_TABLE, schema=_chunks_schema(dim))
        if META_TABLE not in existing:
            self._db.create_table(META_TABLE, schema=_META_SCHEMA)

    def drop_tables(self) -> None:
        """Drop all tables (used in tests or force-rebuild)."""
        existing = self._table_names()
        for name in (FILES_TABLE, CHUNKS_TABLE, META_TABLE):
            if name in existing:
                self._db.drop_table(name)

    def tables_exist(self) -> bool:
        """Return True if the index tables (files and chunks) both exist."""
        existing = self._table_names()
        return FILES_TABLE in existing and CHUNKS_TABLE in existing

    # ------------------------------------------------------------------ meta

    def get_meta(self, key: str) -> str | None:
        """Return stored metadata value for key, or None if missing."""
        if META_TABLE not in self._table_names():
            return None
        rows = (
            self._db.open_table(META_TABLE)
            .search()
            .where(f"key = '{_esc(key)}'", prefilter=True)
            .limit(1)
            .to_list()
        )
        return rows[0]["value"] if rows else None

    def set_meta(self, key: str, value: str) -> None:
        """Store or overwrite a metadata key-value pair."""
        tbl = self._db.open_table(META_TABLE)
        tbl.delete(f"key = '{_esc(key)}'")
        tbl.add([{"key": key, "value": value}])

    # ------------------------------------------------------------------ files

    def _files_tbl(self):  # type: ignore[return]
        return self._db.open_table(FILES_TABLE)

    def get_file_meta(self, path: str) -> dict | None:
        """Return stored metadata for path, or None if not indexed."""
        tbl = self._files_tbl()
        rows = tbl.search().where(f"path = '{_esc(path)}'", prefilter=True).limit(1).to_list()
        return rows[0] if rows else None

    def upsert_file_meta(self, path: str, size: int, mtime: float, file_hash: str) -> None:
        """Insert or overwrite file metadata record."""
        tbl = self._files_tbl()
        tbl.delete(f"path = '{_esc(path)}'")
        tbl.add([{"path": path, "size": size, "mtime": mtime, "file_hash": file_hash}])

    def delete_file_meta(self, path: str) -> None:
        """Remove file metadata record."""
        self._files_tbl().delete(f"path = '{_esc(path)}'")

    def list_indexed_paths(self) -> list[str]:
        """Return all paths currently in files table."""
        rows = self._files_tbl().search().select(["path"]).to_list()
        return [r["path"] for r in rows]

    def get_paths_by_hash(self, file_hash: str) -> list[str]:
        """Return all file paths that share the given content hash."""
        rows = (
            self._files_tbl()
            .search()
            .where(f"file_hash = '{_esc(file_hash)}'", prefilter=True)
            .select(["path"])
            .to_list()
        )
        return [r["path"] for r in rows]

    # ------------------------------------------------------------------ chunks

    def _chunks_tbl(self):  # type: ignore[return]
        return self._db.open_table(CHUNKS_TABLE)

    def hash_has_chunks(self, file_hash: str) -> bool:
        """Return True if at least one chunk exists for this file_hash."""
        rows = (
            self._chunks_tbl()
            .search()
            .where(f"file_hash = '{_esc(file_hash)}'", prefilter=True)
            .limit(1)
            .to_list()
        )
        return len(rows) > 0

    def add_chunks(self, records: list[dict]) -> None:
        """Bulk-insert chunk records (file_hash/chunk_index/start/end/content/vector)."""
        self._chunks_tbl().add(records)

    def delete_chunks_by_hash(self, file_hash: str) -> None:
        """Delete all chunks for this file_hash."""
        self._chunks_tbl().delete(f"file_hash = '{_esc(file_hash)}'")

    def query(self, vector: list[float], top_k: int) -> list[dict]:
        """Cosine ANN; returns dicts: file_hash/chunk_index/start/end/content/_distance."""
        return (
            self._chunks_tbl()
            .search(vector, vector_column_name="vector")
            .metric("cosine")
            .limit(top_k)
            .select(["file_hash", "chunk_index", "start", "end", "content"])
            .to_list()
        )


def _esc(value: str) -> str:
    """Escape single quotes in SQL string literals."""
    return value.replace("'", "''")
