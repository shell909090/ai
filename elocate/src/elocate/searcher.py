"""Searcher: vector recall with optional regex post-filter."""

import logging
import re
from dataclasses import dataclass

from elocate.config import Config
from elocate.db import VectorDB
from elocate.embedder import Embedder

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """A single search result."""

    path: str
    score: float
    snippet: str = ""


class Searcher:
    """Performs vector search with optional regex post-filter."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._db = VectorDB(config.index_path)

    def search(self, query: str, pattern: str | None = None) -> list[SearchResult]:
        """Search by query; optionally filter results whose path/content match pattern."""
        raise NotImplementedError
