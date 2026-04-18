"""Index builder: incremental scanning with file-hash reference counting."""

import hashlib
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
        embedder = Embedder(self._config.embedding_model)
        self._db.init_tables(embedder.dim)
        chunker = Chunker(self._config.chunk_size, self._config.chunk_overlap)

        disk_files = self._collect_files()
        disk_paths = {str(p) for p, _ in disk_files}
        indexed_paths = set(self._db.list_indexed_paths())

        removed = self._remove_deleted(indexed_paths - disk_paths)
        to_embed, added, updated = self._scan_disk_files(disk_files)

        for i in range(0, len(to_embed), BATCH_SIZE):
            self._index_batch(to_embed[i : i + BATCH_SIZE], embedder, chunker)

        return added, updated, removed

    def _remove_deleted(self, gone: set[str]) -> int:
        """Delete index entries for files no longer on disk; return count."""
        removed = 0
        for path_str in gone:
            meta = self._db.get_file_meta(path_str)
            if meta:
                self._db.delete_file_meta(path_str)
                old_hash = meta["file_hash"]
                if not self._db.get_paths_by_hash(old_hash):
                    self._db.delete_chunks_by_hash(old_hash)
            removed += 1
        return removed

    def _scan_disk_files(
        self, disk_files: list[tuple[Path, DirConfig]]
    ) -> tuple[list[tuple[str, str, int, float, str]], int, int]:
        """Scan disk files; return (to_embed list, added count, updated count)."""
        to_embed: list[tuple[str, str, int, float, str]] = []
        added = updated = 0

        for path, dir_cfg in disk_files:
            path_str = str(path)
            try:
                stat = path.stat()
            except OSError as exc:
                logger.warning("Cannot stat %s: %s", path_str, exc)
                continue

            rec = self._db.get_file_meta(path_str)
            if rec and rec["size"] == stat.st_size and rec["mtime"] == stat.st_mtime:
                continue  # unchanged

            try:
                file_hash = self._file_hash(path)
            except OSError as exc:
                logger.warning("Cannot hash %s: %s", path_str, exc)
                continue

            added, updated = self._handle_file(
                path_str, stat, file_hash, dir_cfg, rec, to_embed, added, updated
            )

        return to_embed, added, updated

    def _handle_file(
        self,
        path_str: str,
        stat: object,
        file_hash: str,
        dir_cfg: DirConfig,
        rec: dict | None,
        to_embed: list,
        added: int,
        updated: int,
    ) -> tuple[int, int]:
        """Process a single changed/new file; mutate to_embed as needed."""

        size = stat.st_size  # type: ignore[union-attr]
        mtime = stat.st_mtime  # type: ignore[union-attr]

        if rec:
            if file_hash == rec["file_hash"]:
                self._db.upsert_file_meta(path_str, size, mtime, file_hash)
                return added, updated + 1
            old_hash = rec["file_hash"]
            self._db.delete_file_meta(path_str)
            if not self._db.get_paths_by_hash(old_hash):
                self._db.delete_chunks_by_hash(old_hash)
            updated += 1
        else:
            added += 1

        if self._db.hash_has_chunks(file_hash):
            self._db.upsert_file_meta(path_str, size, mtime, file_hash)
            return added, updated

        try:
            text = self._extract_text(Path(path_str), dir_cfg)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Cannot extract text from %s: %s", path_str, exc)
            return added, updated

        to_embed.append((path_str, file_hash, size, mtime, text))
        return added, updated

    def _index_batch(
        self,
        batch: list[tuple[str, str, int, float, str]],
        embedder: Embedder,
        chunker: Chunker,
    ) -> None:
        """Chunk, embed and store a batch of (path, hash, size, mtime, text) tuples."""
        all_chunks: list[dict] = []
        file_metas: list[tuple[str, int, float, str]] = []

        for path_str, file_hash, size, mtime, text in batch:
            chunks = chunker.chunk(text)
            texts = [c.content for c in chunks] if chunks else [""]
            vectors = embedder.embed(texts)

            for chunk, vec in zip(chunks if chunks else [None], vectors):
                all_chunks.append(
                    {
                        "file_hash": file_hash,
                        "chunk_index": chunk.chunk_index if chunk else 0,
                        "start": chunk.start if chunk else 0,
                        "end": chunk.end if chunk else 0,
                        "content": chunk.content if chunk else "",
                        "vector": vec.tolist(),
                    }
                )
            file_metas.append((path_str, size, mtime, file_hash))

        if all_chunks:
            self._db.add_chunks(all_chunks)
        for path_str, size, mtime, file_hash in file_metas:
            self._db.upsert_file_meta(path_str, size, mtime, file_hash)

    def _collect_files(self) -> list[tuple[Path, DirConfig]]:
        """Collect (file_path, dir_config) pairs from all configured dirs."""
        result: list[tuple[Path, DirConfig]] = []
        for dir_cfg in self._config.dirs:
            base = Path(dir_cfg.path).expanduser()
            if not base.is_dir():
                logger.warning("Directory does not exist, skipping: %s", base)
                continue
            for ext in dir_cfg.extensions:
                for fp in base.rglob(f"*{ext}"):
                    if fp.is_file():
                        result.append((fp, dir_cfg))
        return result

    def _file_hash(self, path: Path) -> str:
        """Compute SHA-256 hex digest of file content."""
        h = hashlib.sha256()
        with path.open("rb") as f:
            for block in iter(lambda: f.read(65536), b""):
                h.update(block)
        return h.hexdigest()

    def _extract_text(self, path: Path, dir_cfg: DirConfig) -> str:
        """Extract plain text from path using the dir's configured extractor."""
        if dir_cfg.extractor == "plaintext":
            return path.read_text(errors="replace")

        if dir_cfg.extractor == "all2txt":
            try:
                import all2txt  # type: ignore[import-untyped]
            except ImportError as exc:
                raise ImportError(
                    "all2txt is not installed. Install it with: pip install elocate[all2txt]"
                ) from exc

            registry = all2txt.registry
            old_config = registry.get_config() if hasattr(registry, "get_config") else None
            try:
                if dir_cfg.extractor_config:
                    cfg = all2txt.Config(**dir_cfg.extractor_config)
                    registry.configure(cfg)
                return registry.extract(path)
            finally:
                if old_config is not None:
                    registry.configure(old_config)

        raise ValueError(f"Unknown extractor: {dir_cfg.extractor!r}")
