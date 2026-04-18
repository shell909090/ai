"""Searcher: vector recall with optional regex post-filter."""

import logging
import re
from dataclasses import dataclass, field

from elocate.config import Config
from elocate.db import VectorDB
from elocate.embedder import Embedder

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """A single search result."""

    paths: list[str]  # all file paths sharing this chunk's file_hash
    file_hash: str
    chunk_index: int
    start: int
    end: int
    score: float  # 1 - cosine_distance, higher is more relevant
    snippet: str = field(default="")  # content[:200]


class Searcher:
    """Performs vector search with optional regex post-filter."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._db = VectorDB(config.index_path)

    def search(self, query: str, pattern: str | None = None) -> list[SearchResult]:
        """Embed query → ANN recall top_k → optional regex filter on paths+content."""
        if not self._db.tables_exist():
            raise RuntimeError("No index found. Run 'elocate-updatedb' first.")

        embedder = Embedder(self._config.embedding_model)
        vec = embedder.embed([query])[0].tolist()
        raw = self._db.query(vec, self._config.top_k)

        compiled = re.compile(pattern) if pattern else None

        results: list[SearchResult] = []
        for row in raw:
            file_hash = row["file_hash"]
            paths = self._db.get_paths_by_hash(file_hash)
            content = row.get("content", "")
            score = 1.0 - float(row.get("_distance", 0.0))

            if compiled:
                hit = any(compiled.search(p) for p in paths) or compiled.search(content)
                if not hit:
                    continue

            results.append(
                SearchResult(
                    paths=paths,
                    file_hash=file_hash,
                    chunk_index=row["chunk_index"],
                    start=row["start"],
                    end=row["end"],
                    score=score,
                    snippet=content[:200],
                )
            )

        results.sort(key=lambda r: r.score, reverse=True)
        return results
