"""Index builder: incremental scanning with file-hash reference counting."""

import fnmatch
import hashlib
import logging
from pathlib import Path

from elocate.chunker import Chunker
from elocate.config import Config, DirConfig
from elocate.db import VectorDB
from elocate.embedder import Embedder

logger = logging.getLogger(__name__)

_OPENAI_BACKEND = "openai"

BATCH_SIZE = 64
MIN_FILE_BYTES = 4  # files smaller than this have no search value (< ~2 CJK chars)


class Indexer:
    """Builds and maintains the document vector index incrementally."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._db = VectorDB(config.index_path)

    def run(self) -> tuple[int, int, int]:
        """Incremental index update. Returns (added, updated, removed) file counts."""
        embedder = Embedder(
            self._config.embedding_model,
            api_base=self._config.openai_base_url,
            api_key=self._config.openai_api_key,
        )

        # B002: if model/backend changed since last run, force full rebuild
        if self._db.tables_exist():
            stored_model = self._db.get_meta("embedding_model")
            stored_backend = self._db.get_meta("embedder_backend")
            if stored_model != self._config.embedding_model or stored_backend != _OPENAI_BACKEND:
                logger.info(
                    "Embedding config changed (%s/%s → %s/%s); rebuilding index.",
                    stored_backend,
                    stored_model,
                    _OPENAI_BACKEND,
                    self._config.embedding_model,
                )
                self._db.drop_tables()

        self._db.init_tables(embedder.dim)
        self._db.set_meta("embedding_model", self._config.embedding_model)
        self._db.set_meta("embedder_backend", _OPENAI_BACKEND)

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
    ) -> tuple[list[tuple[str, str, int, float, str, str | None]], int, int]:
        """Scan disk files; return (to_embed list, added count, updated count)."""
        to_embed: list[tuple[str, str, int, float, str, str | None]] = []
        added = updated = 0

        for path, dir_cfg in disk_files:
            path_str = str(path)
            try:
                stat = path.stat()
            except OSError as exc:
                logger.warning("Cannot stat %s: %s", path_str, exc)
                continue

            if stat.st_size < MIN_FILE_BYTES:
                continue  # too small to be meaningful

            rec = self._db.get_file_meta(path_str)
            if rec and rec["size"] == stat.st_size and rec["mtime"] == stat.st_mtime:
                continue  # unchanged

            try:
                file_hash = self._file_hash(path)
            except OSError as exc:
                logger.warning("Cannot hash %s: %s", path_str, exc)
                continue

            action = self._handle_file(path_str, stat, file_hash, dir_cfg, rec, to_embed)
            if action == "added":
                added += 1
            elif action == "updated":
                updated += 1

        return to_embed, added, updated

    def _handle_file(
        self,
        path_str: str,
        stat: object,
        file_hash: str,
        dir_cfg: DirConfig,
        rec: dict | None,
        to_embed: list,
    ) -> str | None:
        """Process a single changed/new file; mutate to_embed as needed. Returns action or None."""
        size = stat.st_size  # type: ignore[union-attr]
        mtime = stat.st_mtime  # type: ignore[union-attr]

        old_hash: str | None = rec["file_hash"] if rec else None

        if rec and file_hash == old_hash:
            # Metadata drift (size/mtime) but content identical — just refresh metadata
            self._db.upsert_file_meta(path_str, size, mtime, file_hash)
            return "updated"

        # Content changed or new file.
        # B001: extract text BEFORE touching existing index so failures leave old data intact.
        if not self._db.hash_has_chunks(file_hash):
            try:
                text = self._extract_text(Path(path_str), dir_cfg)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Cannot extract text from %s: %s", path_str, exc)
                return None  # old index preserved

            to_embed.append((path_str, file_hash, size, mtime, text, old_hash))
            return "updated" if rec else "added"

        # New hash already indexed — update metadata and clean up old hash if unreferenced
        self._db.upsert_file_meta(path_str, size, mtime, file_hash)
        if old_hash is not None and not self._db.get_paths_by_hash(old_hash):
            self._db.delete_chunks_by_hash(old_hash)
        return "updated" if rec else "added"

    def _index_batch(
        self,
        batch: list[tuple[str, str, int, float, str, str | None]],
        embedder: Embedder,
        chunker: Chunker,
    ) -> None:
        """Chunk, embed (single call), and store a batch of files."""
        # Phase 1: chunk all files; files with no chunks are still tracked in file_meta
        # so that subsequent runs don't re-process them on every invocation.
        per_file: list[tuple[str, str, int, float, str | None, list]] = []
        for path_str, file_hash, size, mtime, text, old_hash in batch:
            chunks = chunker.chunk(text)
            if not chunks:
                logger.warning("No chunks produced for %s; recording metadata only.", path_str)
                self._db.upsert_file_meta(path_str, size, mtime, file_hash)
                if old_hash is not None and not self._db.get_paths_by_hash(old_hash):
                    self._db.delete_chunks_by_hash(old_hash)
                continue
            per_file.append((path_str, file_hash, size, mtime, old_hash, chunks))

        if not per_file:
            return

        # Phase 2: single embed call across all chunks in this batch
        all_texts = [c.content for _, _, _, _, _, chunks in per_file for c in chunks]
        all_vectors = embedder.embed(all_texts)

        # Phase 3: distribute vectors and write
        all_chunk_records: list[dict] = []
        file_metas: list[tuple[str, int, float, str, str | None]] = []
        offset = 0
        for path_str, file_hash, size, mtime, old_hash, chunks in per_file:
            n = len(chunks)
            file_vectors = all_vectors[offset : offset + n]
            offset += n
            for chunk, vec in zip(chunks, file_vectors):
                all_chunk_records.append(
                    {
                        "file_hash": file_hash,
                        "chunk_index": chunk.chunk_index,
                        "start": chunk.start,
                        "end": chunk.end,
                        "content": chunk.content,
                        "vector": vec.tolist(),
                    }
                )
            file_metas.append((path_str, size, mtime, file_hash, old_hash))

        if all_chunk_records:
            self._db.add_chunks(all_chunk_records)
        for path_str, size, mtime, file_hash, old_hash in file_metas:
            self._db.upsert_file_meta(path_str, size, mtime, file_hash)
            # B001: clean up old hash AFTER successful write
            if old_hash is not None and not self._db.get_paths_by_hash(old_hash):
                self._db.delete_chunks_by_hash(old_hash)

    def _collect_files(self) -> list[tuple[Path, DirConfig]]:
        """Collect (file_path, dir_config) pairs matching any configured rule."""
        result: list[tuple[Path, DirConfig]] = []
        seen: set[str] = set()
        for dir_cfg in self._config.dirs:
            base = Path(dir_cfg.path).expanduser()
            if not base.is_dir():
                logger.warning("Directory does not exist, skipping: %s", base)
                continue
            for fp in base.rglob("*"):
                if fp.is_file() and self._matches_extensions(fp, dir_cfg.extensions):
                    path_str = str(fp)
                    if path_str not in seen:
                        seen.add(path_str)
                        result.append((fp, dir_cfg))
        return result

    def _match_extension_rule(self, path: Path, rule: str) -> bool:
        """Check whether a file path matches one configured extension rule."""
        path_name = path.name.lower()
        suffix = path.suffix.lower()

        if rule.startswith("suffix:"):
            return path_name.endswith(rule.removeprefix("suffix:"))

        if rule.startswith("glob:"):
            return fnmatch.fnmatchcase(path_name, rule.removeprefix("glob:"))

        return suffix == rule

    def _matches_extensions(self, path: Path, rules: list[str]) -> bool:
        """Return True when path matches any configured extension rule."""
        return any(self._match_extension_rule(path, rule) for rule in rules)

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
                import all2txt.backends  # noqa: F401 — triggers backend registration
                from all2txt import registry
                from all2txt.core.config import Config as All2txtConfig
            except ImportError as exc:
                raise ImportError(
                    "all2txt is not installed. Install it with: pip install elocate[all2txt]"
                ) from exc

            if dir_cfg.extractor_config:
                cfg = All2txtConfig(**dir_cfg.extractor_config)
                registry.configure(cfg)
            return registry.extract(path)

        raise ValueError(f"Unknown extractor: {dir_cfg.extractor!r}")
