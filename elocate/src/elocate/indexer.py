"""Index builder: incremental scanning with file-hash reference counting."""

import logging
from pathlib import Path

from elocate.chunker import Chunker
from elocate.config import Config, DirConfig
from elocate.db import VectorDB
from elocate.embedder import Embedder

logger = logging.getLogger(__name__)

BATCH_SIZE = 64


class Indexer:
    """Builds and maintains the document vector index incrementally."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._db = VectorDB(config.index_path)

    def run(self) -> tuple[int, int, int]:
        """Incremental index update. Returns (added, updated, removed) file counts."""
        raise NotImplementedError

    def _collect_files(self) -> list[tuple[Path, DirConfig]]:
        """Collect (file_path, dir_config) pairs from all configured dirs."""
        raise NotImplementedError

    def _file_hash(self, path: Path) -> str:
        """Compute SHA-256 hex digest of file content."""
        raise NotImplementedError

    def _extract_text(self, path: Path, dir_cfg: DirConfig) -> str:
        """Extract plain text from path using the dir's configured extractor.

        "plaintext": read directly as UTF-8.
        "all2txt":   configure all2txt registry with dir_cfg.extractor_config,
                     call registry.extract(path), then restore registry state.
        """
        raise NotImplementedError
