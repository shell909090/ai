"""LanceDB interface for vector index operations."""

import logging
from pathlib import Path

import pyarrow as pa

logger = logging.getLogger(__name__)

TABLE_NAME = "documents"


class VectorDB:
    """Wraps LanceDB for document vector storage and retrieval."""

    def __init__(self, index_path: Path) -> None:
        import lancedb  # deferred to avoid slow import at CLI startup

        index_path.mkdir(parents=True, exist_ok=True)
        self._db = lancedb.connect(str(index_path))

    def create_table(self, dim: int) -> None:
        """Create the documents table with the given embedding dimension."""
        schema = pa.schema([
            pa.field("path", pa.utf8()),
            pa.field("content", pa.utf8()),
            pa.field("vector", pa.list_(pa.float32(), dim)),
        ])
        self._db.create_table(TABLE_NAME, schema=schema)
        logger.debug("Created table '%s' with dim=%d", TABLE_NAME, dim)

    def drop_table(self) -> None:
        """Drop the documents table if it exists."""
        if TABLE_NAME in self._db.table_names():
            self._db.drop_table(TABLE_NAME)
            logger.debug("Dropped table '%s'", TABLE_NAME)

    def upsert(self, records: list[dict]) -> None:
        """Write records into the documents table."""
        tbl = self._db.open_table(TABLE_NAME)
        tbl.add(records)
        logger.debug("Upserted %d records", len(records))

    def query(self, vector: list[float], top_k: int) -> list[dict]:
        """Return top_k most similar documents as a list of dicts."""
        tbl = self._db.open_table(TABLE_NAME)
        results = tbl.search(vector).limit(top_k).to_list()
        return results  # type: ignore[return-value]

    def table_exists(self) -> bool:
        """Check whether the documents table exists."""
        return TABLE_NAME in self._db.table_names()
