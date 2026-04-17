"""Index builder: scans directories and stores document vectors in LanceDB."""

import logging
from pathlib import Path

from elocate.config import Config
from elocate.db import VectorDB
from elocate.embedder import Embedder

logger = logging.getLogger(__name__)

BATCH_SIZE = 64


class Indexer:
    """Builds the document vector index by scanning configured directories."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._db = VectorDB(config.index_path)

    def run(self) -> int:
        """Scan directories and rebuild the index. Returns indexed document count."""
        raise NotImplementedError

    def _collect_files(self) -> list[Path]:
        """Collect all indexable files from configured index_dirs."""
        files: list[Path] = []
        for dir_str in self._config.index_dirs:
            d = Path(dir_str).expanduser()
            if not d.is_dir():
                logger.warning("index_dir not found or not a directory: %s", d)
                continue
            for ext in self._config.file_extensions:
                files.extend(d.rglob(f"*{ext}"))
        return files
