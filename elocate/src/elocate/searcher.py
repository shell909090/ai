"""Searcher: vector recall with optional regex post-filter."""

import logging
from dataclasses import dataclass, field

from elocate.config import Config
from elocate.db import VectorDB
from elocate.embedder import Embedder

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """A single search result."""

    paths: list[str]   # all file paths sharing this chunk's file_hash
    file_hash: str
    chunk_index: int
    start: int
    end: int
    score: float       # 1 - cosine_distance, higher is more relevant
    snippet: str = field(default="")  # content[:200]


class Searcher:
    """Performs vector search with optional regex post-filter."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._db = VectorDB(config.index_path)

    def search(self, query: str, pattern: str | None = None) -> list[SearchResult]:
        """Embed query → ANN recall top_k → optional regex filter on paths+content."""
        raise NotImplementedError
