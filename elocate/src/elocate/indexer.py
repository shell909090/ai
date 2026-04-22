"""Index builder: incremental scanning with file-hash reference counting."""

import fnmatch
import hashlib
import logging
import math
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from elocate.chunker import Chunker
from elocate.config import Config, DirConfig
from elocate.db import VectorDB
from elocate.embedder import Embedder

logger = logging.getLogger(__name__)

_OPENAI_BACKEND = "openai"
_INDEX_SCHEMA_VERSION = "2"
MIN_FILE_BYTES = 4  # files smaller than this have no search value (< ~2 CJK chars)
_SUMMARY_SYSTEM_PROMPT = (
    "You prepare retrieval summaries for local file search. "
    "Summarize only what is explicitly supported by the input text. "
    "Do not invent facts, names, claims, or details that do not appear in the source. "
    "Write one concise summary in the same language as the source when possible."
)


@dataclass
class PendingFile:
    """A file that still needs text extraction before embedding."""

    path: str
    file_hash: str
    size: int
    mtime: float
    dir_cfg: DirConfig
    old_hash: str | None


@dataclass
class BatchItem:
    """A file whose extracted text is waiting to be embedded."""

    path: str
    file_hash: str
    size: int
    mtime: float
    index_text: str
    index_route: str
    text_entropy: float
    median_paragraph_length: int
    old_hash: str | None


@dataclass
class PerfStats:
    """Accumulates debug-level indexing performance counters."""

    files_scanned: int = 0
    files_skipped_unchanged: int = 0
    files_pending: int = 0
    files_extract_failed: int = 0
    files_flushed: int = 0
    chunks_embedded: int = 0
    chars_embedded: int = 0
    extract_seconds_total: float = 0.0
    chunk_seconds_total: float = 0.0
    embed_seconds_total: float = 0.0
    db_write_seconds_total: float = 0.0
    batch_extract_seconds: float = 0.0
    batch_index: int = 0

    def reset_batch_extract(self) -> None:
        """Reset the extraction timer for the next flush window."""
        self.batch_extract_seconds = 0.0


@dataclass
class ChunkedFile:
    """A file with prepared chunks waiting for embedding/write."""

    path: str
    file_hash: str
    size: int
    mtime: float
    old_hash: str | None
    action: str
    index_route: str
    text_entropy: float
    median_paragraph_length: int
    chunks: list["IndexedChunk"]


@dataclass
class IndexedChunk:
    """A chunk record ready for embedding and persistence."""

    content: str
    chunk_index: int
    start: int
    end: int
    content_kind: str


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

        # B002: if model/backend/indexing semantics changed since last run, force rebuild
        if self._db.tables_exist():
            stored_schema = self._db.get_meta("index_schema_version")
            stored_model = self._db.get_meta("embedding_model")
            stored_backend = self._db.get_meta("embedder_backend")
            stored_chunk_size = self._db.get_meta("chunk_size")
            stored_chunk_overlap = self._db.get_meta("chunk_overlap")
            stored_summary_model = self._db.get_meta("summary_model")
            stored_entropy_min = self._db.get_meta("rag_entropy_min")
            stored_entropy_max = self._db.get_meta("rag_entropy_max")
            stored_min_para = self._db.get_meta("rag_min_paragraph_length")
            if (
                stored_schema != _INDEX_SCHEMA_VERSION
                or stored_model != self._config.embedding_model
                or stored_backend != _OPENAI_BACKEND
                or stored_chunk_size != str(self._config.chunk_size)
                or stored_chunk_overlap != str(self._config.chunk_overlap)
                or stored_summary_model != self._config.summary_model
                or stored_entropy_min != str(self._config.rag_entropy_min)
                or stored_entropy_max != str(self._config.rag_entropy_max)
                or stored_min_para != str(self._config.rag_min_paragraph_length)
            ):
                logger.info(
                    "Index config changed; rebuilding index. "
                    "schema=%s→%s backend/model=%s/%s→%s/%s summary_model=%s→%s",
                    stored_schema,
                    _INDEX_SCHEMA_VERSION,
                    stored_backend,
                    stored_model,
                    _OPENAI_BACKEND,
                    self._config.embedding_model,
                    stored_summary_model,
                    self._config.summary_model,
                )
                self._db.drop_tables()

        self._db.init_tables(embedder.dim)
        self._db.set_meta("index_schema_version", _INDEX_SCHEMA_VERSION)
        self._db.set_meta("embedding_model", self._config.embedding_model)
        self._db.set_meta("embedder_backend", _OPENAI_BACKEND)
        self._db.set_meta("chunk_size", str(self._config.chunk_size))
        self._db.set_meta("chunk_overlap", str(self._config.chunk_overlap))
        self._db.set_meta("summary_model", self._config.summary_model)
        self._db.set_meta("rag_entropy_min", str(self._config.rag_entropy_min))
        self._db.set_meta("rag_entropy_max", str(self._config.rag_entropy_max))
        self._db.set_meta("rag_min_paragraph_length", str(self._config.rag_min_paragraph_length))

        chunker = Chunker(self._config.chunk_size, self._config.chunk_overlap)
        perf = PerfStats()
        self._log_route_config()

        disk_files = self._collect_files()
        disk_paths = {str(p) for p, _ in disk_files}
        indexed_paths = set(self._db.list_indexed_paths())

        removed = self._remove_deleted(indexed_paths - disk_paths)
        pending_files, added, updated = self._scan_disk_files(disk_files, perf)
        flushed_added, flushed_updated = self._flush_pending_files(
            pending_files, embedder, chunker, perf
        )
        added += flushed_added
        updated += flushed_updated
        self._log_perf_summary(perf)

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
        self,
        disk_files: list[tuple[Path, DirConfig]],
        perf: PerfStats,
    ) -> tuple[list[PendingFile], int, int]:
        """Scan disk files; return pending files plus added/updated counts."""
        pending_files: list[PendingFile] = []
        added = updated = 0

        for path, dir_cfg in disk_files:
            perf.files_scanned += 1
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
                perf.files_skipped_unchanged += 1
                continue  # unchanged

            try:
                file_hash = self._file_hash(path)
            except OSError as exc:
                logger.warning("Cannot hash %s: %s", path_str, exc)
                continue

            action, pending = self._plan_file(path_str, stat, file_hash, dir_cfg, rec)
            if pending is not None:
                pending_files.append(pending)
                perf.files_pending += 1
            elif action == "added":
                added += 1
            elif action == "updated":
                updated += 1

        return pending_files, added, updated

    def _plan_file(
        self,
        path_str: str,
        stat: os.stat_result,
        file_hash: str,
        dir_cfg: DirConfig,
        rec: dict | None,
    ) -> tuple[str | None, PendingFile | None]:
        """Plan how a changed/new file should be processed."""
        size = stat.st_size
        mtime = stat.st_mtime

        old_hash: str | None = rec["file_hash"] if rec else None

        if rec and file_hash == old_hash:
            # Metadata drift (size/mtime) but content identical — just refresh metadata
            self._db.upsert_file_meta(
                path_str,
                size,
                mtime,
                file_hash,
                index_route=rec.get("index_route", "raw"),
                text_entropy=float(rec.get("text_entropy", 0.0)),
                median_paragraph_length=int(rec.get("median_paragraph_length", 0)),
            )
            self._log_file_written(
                path=path_str,
                action="updated",
                status="metadata_refreshed",
                index_route=rec.get("index_route", "raw"),
                text_entropy=float(rec.get("text_entropy", 0.0)),
                median_paragraph_length=int(rec.get("median_paragraph_length", 0)),
                chunks=0,
            )
            return "updated", None

        # Content changed or new file.
        # B001: extract text BEFORE touching existing index so failures leave old data intact.
        if not self._db.hash_has_chunks(file_hash):
            return (
                "updated" if rec else "added",
                PendingFile(
                    path=path_str,
                    file_hash=file_hash,
                    size=size,
                    mtime=mtime,
                    dir_cfg=dir_cfg,
                    old_hash=old_hash,
                ),
            )

        # New hash already indexed — update metadata and clean up old hash if unreferenced
        existing = self._db.get_file_meta_by_hash(file_hash)
        index_route = existing.get("index_route", "raw") if existing else "raw"
        text_entropy = float(existing.get("text_entropy", 0.0)) if existing else 0.0
        median_paragraph_length = int(existing.get("median_paragraph_length", 0)) if existing else 0
        self._db.upsert_file_meta(
            path_str,
            size,
            mtime,
            file_hash,
            index_route=index_route,
            text_entropy=text_entropy,
            median_paragraph_length=median_paragraph_length,
        )
        if old_hash is not None and not self._db.get_paths_by_hash(old_hash):
            self._db.delete_chunks_by_hash(old_hash)
        self._log_file_written(
            path=path_str,
            action="updated" if rec else "added",
            status="reused_chunks",
            index_route=index_route,
            text_entropy=text_entropy,
            median_paragraph_length=median_paragraph_length,
            chunks=0,
        )
        return "updated" if rec else "added", None

    def _flush_pending_files(
        self,
        pending_files: list[PendingFile],
        embedder: Embedder,
        chunker: Chunker,
        perf: PerfStats,
    ) -> tuple[int, int]:
        """Extract pending files, flush them in batches, and return added/updated counts."""
        batch: list[BatchItem] = []
        batch_chars = 0
        added = 0
        updated = 0

        for pending in pending_files:
            extract_started = time.perf_counter()
            try:
                text = self._extract_text(Path(pending.path), pending.dir_cfg)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Cannot extract text from %s: %s", pending.path, exc)
                perf.files_extract_failed += 1
                continue

            extract_seconds = time.perf_counter() - extract_started
            perf.extract_seconds_total += extract_seconds
            perf.batch_extract_seconds += extract_seconds
            text_entropy = self._text_entropy(text)
            median_paragraph_length = self._median_paragraph_length(text)
            index_route, route_reason = self._route_decision(text_entropy, median_paragraph_length)
            self._log_route_decision(
                path=pending.path,
                text_entropy=text_entropy,
                median_paragraph_length=median_paragraph_length,
                index_route=index_route,
                reason=route_reason,
            )
            try:
                index_text = text
                if index_route == "summary":
                    summary_started = time.perf_counter()
                    logger.debug(
                        "Summary start: path=%s model=%s input_chars=%d",
                        pending.path,
                        self._config.summary_model,
                        len(text),
                    )
                    index_text = self._summarize_text(text)
                    self._log_summary_metrics(
                        path=pending.path,
                        input_chars=len(text),
                        output_chars=len(index_text),
                        seconds=time.perf_counter() - summary_started,
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Cannot summarize %s: %s", pending.path, exc)
                perf.files_extract_failed += 1
                continue

            batch.append(
                BatchItem(
                    path=pending.path,
                    file_hash=pending.file_hash,
                    size=pending.size,
                    mtime=pending.mtime,
                    index_text=index_text,
                    index_route=index_route,
                    text_entropy=text_entropy,
                    median_paragraph_length=median_paragraph_length,
                    old_hash=pending.old_hash,
                )
            )
            batch_chars += len(index_text)

            if self._should_flush_batch(batch, batch_chars):
                batch_added, batch_updated = self._index_batch(
                    batch, embedder, chunker, perf, batch_chars
                )
                added += batch_added
                updated += batch_updated
                batch = []
                batch_chars = 0

        if batch:
            batch_added, batch_updated = self._index_batch(
                batch, embedder, chunker, perf, batch_chars
            )
            added += batch_added
            updated += batch_updated

        return added, updated

    def _should_flush_batch(self, batch: list[BatchItem], batch_chars: int) -> bool:
        """Return True when the current extracted batch should be flushed."""
        return (
            len(batch) >= self._config.embed_batch_files
            or batch_chars >= self._config.embed_batch_chars
        )

    def _text_entropy(self, text: str) -> float:
        """Compute character-level Shannon entropy for extracted text."""
        if not text:
            return 0.0
        counts: dict[str, int] = {}
        for ch in text:
            counts[ch] = counts.get(ch, 0) + 1
        total = len(text)
        entropy = 0.0
        for count in counts.values():
            p = count / total
            entropy -= p * math.log2(p)
        return entropy

    def _median_paragraph_length(self, text: str) -> int:
        """Compute the median length of non-empty paragraphs split by blank lines."""
        if not text:
            return 0
        lengths = sorted(len(part.strip()) for part in re.split(r"\n\s*\n+", text) if part.strip())
        if not lengths:
            return 0
        mid = len(lengths) // 2
        if len(lengths) % 2 == 1:
            return lengths[mid]
        return (lengths[mid - 1] + lengths[mid]) // 2

    def _choose_index_route(
        self,
        text_entropy: float,
        median_paragraph_length: int,
    ) -> str:
        """Choose whether one file should use raw chunks or a summary chunk."""
        route, _ = self._route_decision(text_entropy, median_paragraph_length)
        return route

    def _route_decision(
        self,
        text_entropy: float,
        median_paragraph_length: int,
    ) -> tuple[str, str]:
        """Return the chosen route plus the rule that selected it."""
        if text_entropy < self._config.rag_entropy_min:
            return "summary", "entropy_below_min"
        if text_entropy > self._config.rag_entropy_max:
            return "summary", "entropy_above_max"
        if median_paragraph_length < self._config.rag_min_paragraph_length:
            return "summary", "paragraph_length_below_min"
        return "raw", "within_thresholds"

    def _summarize_text(self, text: str) -> str:
        """Generate a factual topic summary for indexing."""
        from openai import OpenAI

        client = OpenAI(
            base_url=self._config.openai_base_url or None,
            api_key=self._config.openai_api_key or "none",
        )
        response = client.chat.completions.create(
            model=self._config.summary_model,
            temperature=0,
            messages=[
                {"role": "system", "content": _SUMMARY_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Summarize this file for semantic retrieval. "
                        "Keep the output concise, mention the main theme and key facts, "
                        "and do not invent anything not supported by the source.\n\n"
                        f"{text}"
                    ),
                },
            ],
        )
        summary = (response.choices[0].message.content or "").strip()
        if not summary:
            raise ValueError("summary model returned empty content")
        return summary

    def _index_batch(
        self,
        batch: list[BatchItem],
        embedder: Embedder,
        chunker: Chunker,
        perf: PerfStats,
        batch_chars: int,
    ) -> tuple[int, int]:
        """Chunk, embed (single call), and store a batch of files."""
        perf.batch_index += 1
        chunk_started = time.perf_counter()
        added, updated, per_file = self._prepare_batch_chunks(batch, chunker)
        chunk_seconds = time.perf_counter() - chunk_started
        perf.chunk_seconds_total += chunk_seconds

        if not per_file:
            self._log_batch_metrics(
                perf=perf,
                files=len(batch),
                chars=batch_chars,
                chunks=0,
                chunk_seconds=chunk_seconds,
                embed_seconds=0.0,
                db_write_seconds=0.0,
            )
            perf.files_flushed += len(batch)
            perf.chars_embedded += batch_chars
            perf.reset_batch_extract()
            return added, updated

        # Phase 2: single embed call across all chunks in this batch
        all_texts = [c.content for item in per_file for c in item.chunks]
        embed_started = time.perf_counter()
        all_vectors = embedder.embed(all_texts)
        embed_seconds = time.perf_counter() - embed_started
        perf.embed_seconds_total += embed_seconds

        # Phase 3: distribute vectors and write
        db_write_started = time.perf_counter()
        added_delta, updated_delta, all_chunk_records = self._write_index_batch(
            per_file, all_vectors
        )
        added += added_delta
        updated += updated_delta

        db_write_seconds = time.perf_counter() - db_write_started
        perf.db_write_seconds_total += db_write_seconds
        perf.files_flushed += len(batch)
        perf.chars_embedded += batch_chars
        perf.chunks_embedded += len(all_chunk_records)
        self._log_batch_metrics(
            perf=perf,
            files=len(batch),
            chars=batch_chars,
            chunks=len(all_chunk_records),
            chunk_seconds=chunk_seconds,
            embed_seconds=embed_seconds,
            db_write_seconds=db_write_seconds,
        )
        perf.reset_batch_extract()
        return added, updated

    def _prepare_batch_chunks(
        self,
        batch: list[BatchItem],
        chunker: Chunker,
    ) -> tuple[int, int, list[ChunkedFile]]:
        """Chunk files and persist metadata for texts that produce no chunks."""
        added = 0
        updated = 0
        per_file: list[ChunkedFile] = []

        for item in batch:
            if item.index_route == "summary":
                chunks = [
                    IndexedChunk(
                        content=item.index_text,
                        chunk_index=0,
                        start=0,
                        end=len(item.index_text),
                        content_kind="summary",
                    )
                ]
            else:
                chunks = [
                    IndexedChunk(
                        content=chunk.content,
                        chunk_index=chunk.chunk_index,
                        start=chunk.start,
                        end=chunk.end,
                        content_kind="raw",
                    )
                    for chunk in chunker.chunk(item.index_text)
                ]
            if not chunks:
                logger.warning("No chunks produced for %s; recording metadata only.", item.path)
                self._db.upsert_file_meta(
                    item.path,
                    item.size,
                    item.mtime,
                    item.file_hash,
                    index_route=item.index_route,
                    text_entropy=item.text_entropy,
                    median_paragraph_length=item.median_paragraph_length,
                )
                if item.old_hash is not None and not self._db.get_paths_by_hash(item.old_hash):
                    self._db.delete_chunks_by_hash(item.old_hash)
                if item.old_hash is None:
                    added += 1
                else:
                    updated += 1
                self._log_file_written(
                    path=item.path,
                    action="added" if item.old_hash is None else "updated",
                    status="metadata_only",
                    index_route=item.index_route,
                    text_entropy=item.text_entropy,
                    median_paragraph_length=item.median_paragraph_length,
                    chunks=0,
                )
                continue

            per_file.append(
                ChunkedFile(
                    path=item.path,
                    file_hash=item.file_hash,
                    size=item.size,
                    mtime=item.mtime,
                    old_hash=item.old_hash,
                    action="added" if item.old_hash is None else "updated",
                    index_route=item.index_route,
                    text_entropy=item.text_entropy,
                    median_paragraph_length=item.median_paragraph_length,
                    chunks=chunks,
                )
            )

        return added, updated, per_file

    def _write_index_batch(
        self,
        per_file: list[ChunkedFile],
        all_vectors: list,
    ) -> tuple[int, int, list[dict]]:
        """Write chunk vectors and file metadata for one prepared batch."""
        added = 0
        updated = 0
        all_chunk_records: list[dict] = []
        offset = 0

        for item in per_file:
            n = len(item.chunks)
            file_vectors = all_vectors[offset : offset + n]
            offset += n
            for chunk, vec in zip(item.chunks, file_vectors):
                all_chunk_records.append(
                    {
                        "file_hash": item.file_hash,
                        "chunk_index": chunk.chunk_index,
                        "start": chunk.start,
                        "end": chunk.end,
                        "content_kind": chunk.content_kind,
                        "content": chunk.content,
                        "vector": vec.tolist(),
                    }
                )

        if all_chunk_records:
            self._db.add_chunks(all_chunk_records)

        for item in per_file:
            self._db.upsert_file_meta(
                item.path,
                item.size,
                item.mtime,
                item.file_hash,
                index_route=item.index_route,
                text_entropy=item.text_entropy,
                median_paragraph_length=item.median_paragraph_length,
            )
            # B001: clean up old hash AFTER successful write
            if item.old_hash is not None and not self._db.get_paths_by_hash(item.old_hash):
                self._db.delete_chunks_by_hash(item.old_hash)
            if item.action == "added":
                added += 1
            else:
                updated += 1
            self._log_file_written(
                path=item.path,
                action=item.action,
                status="written",
                index_route=item.index_route,
                text_entropy=item.text_entropy,
                median_paragraph_length=item.median_paragraph_length,
                chunks=len(item.chunks),
            )

        return added, updated, all_chunk_records

    def _log_route_config(self) -> None:
        """Emit the active routing thresholds for this indexing run."""
        logger.debug(
            "Routing config: summary_model=%s rag_entropy_min=%.3f rag_entropy_max=%.3f "
            "rag_min_paragraph_length=%d",
            self._config.summary_model,
            self._config.rag_entropy_min,
            self._config.rag_entropy_max,
            self._config.rag_min_paragraph_length,
        )

    def _log_route_decision(
        self,
        *,
        path: str,
        text_entropy: float,
        median_paragraph_length: int,
        index_route: str,
        reason: str,
    ) -> None:
        """Emit one debug log for the route chosen for a file."""
        logger.debug(
            "Route decision: path=%s entropy=%.3f median_paragraph_length=%d route=%s reason=%s",
            path,
            text_entropy,
            median_paragraph_length,
            index_route,
            reason,
        )

    def _log_summary_metrics(
        self,
        *,
        path: str,
        input_chars: int,
        output_chars: int,
        seconds: float,
    ) -> None:
        """Emit debug metrics for one summary-model call."""
        raw_chars_per_second = input_chars / seconds if seconds > 0 else 0.0
        summary_chars_per_second = output_chars / seconds if seconds > 0 else 0.0
        logger.debug(
            "Summary done: path=%s model=%s input_chars=%d output_chars=%d "
            "seconds=%.3f raw_chars_per_second=%.1f summary_chars_per_second=%.1f",
            path,
            self._config.summary_model,
            input_chars,
            output_chars,
            seconds,
            raw_chars_per_second,
            summary_chars_per_second,
        )

    def _log_file_written(
        self,
        *,
        path: str,
        action: str,
        status: str,
        index_route: str,
        text_entropy: float,
        median_paragraph_length: int,
        chunks: int,
    ) -> None:
        """Emit one info log after one file has been written or refreshed."""
        logger.info(
            "Indexed file: path=%s action=%s status=%s route=%s chunks=%d "
            "entropy=%.3f median_paragraph_length=%d",
            path,
            action,
            status,
            index_route,
            chunks,
            text_entropy,
            median_paragraph_length,
        )

    def _log_batch_metrics(
        self,
        perf: PerfStats,
        files: int,
        chars: int,
        chunks: int,
        chunk_seconds: float,
        embed_seconds: float,
        db_write_seconds: float,
    ) -> None:
        """Emit debug metrics for one flushed batch."""
        total_seconds = (
            perf.batch_extract_seconds + chunk_seconds + embed_seconds + db_write_seconds
        )
        chars_per_second = chars / total_seconds if total_seconds > 0 else 0.0
        chunks_per_second = chunks / total_seconds if total_seconds > 0 else 0.0
        logger.debug(
            "Batch %d: files=%d chars=%d chunks=%d "
            "extract_seconds=%.3f chunk_seconds=%.3f "
            "embed_seconds=%.3f db_write_seconds=%.3f "
            "chars_per_second=%.1f chunks_per_second=%.1f",
            perf.batch_index,
            files,
            chars,
            chunks,
            perf.batch_extract_seconds,
            chunk_seconds,
            embed_seconds,
            db_write_seconds,
            chars_per_second,
            chunks_per_second,
        )

    def _log_perf_summary(self, perf: PerfStats) -> None:
        """Emit final debug counters for the whole indexing run."""
        logger.debug(
            "Index perf: files_scanned=%d files_skipped_unchanged=%d "
            "files_pending=%d files_extract_failed=%d files_flushed=%d "
            "chars_embedded=%d chunks_embedded=%d "
            "extract_seconds_total=%.3f chunk_seconds_total=%.3f "
            "embed_seconds_total=%.3f db_write_seconds_total=%.3f",
            perf.files_scanned,
            perf.files_skipped_unchanged,
            perf.files_pending,
            perf.files_extract_failed,
            perf.files_flushed,
            perf.chars_embedded,
            perf.chunks_embedded,
            perf.extract_seconds_total,
            perf.chunk_seconds_total,
            perf.embed_seconds_total,
            perf.db_write_seconds_total,
        )

    def _collect_files(self) -> list[tuple[Path, DirConfig]]:
        """Collect (file_path, dir_config) pairs matching any configured rule."""
        result: list[tuple[Path, DirConfig]] = []
        seen: set[str] = set()
        for dir_cfg in self._config.dirs:
            base = Path(dir_cfg.path).expanduser()
            if not base.is_dir():
                logger.warning("Directory does not exist, skipping: %s", base)
                continue
            for root, dirnames, filenames in os.walk(base):
                root_path = Path(root)
                rel_root = "" if root_path == base else root_path.relative_to(base).as_posix()

                dirnames[:] = [
                    name
                    for name in dirnames
                    if not self._matches_exclude(
                        self._join_rel_path(rel_root, name),
                        dir_cfg.exclude,
                    )
                ]

                for name in filenames:
                    rel_path = self._join_rel_path(rel_root, name)
                    if self._matches_exclude(rel_path, dir_cfg.exclude):
                        continue
                    fp = root_path / name
                    if self._matches_extensions(fp, dir_cfg.extensions):
                        path_str = str(fp)
                        if path_str not in seen:
                            seen.add(path_str)
                            result.append((fp, dir_cfg))
        return result

    def _matches_exclude(self, rel_path: str, rules: list[str]) -> bool:
        """Return True when a relative path matches any exclude rule."""
        rel_path = rel_path.lower()
        parts = PurePosixPath(rel_path).parts
        for rule in rules:
            if self._is_name_exclude_rule(rule):
                if rule in parts:
                    return True
                continue
            if fnmatch.fnmatchcase(rel_path, rule):
                return True
        return False

    def _is_name_exclude_rule(self, rule: str) -> bool:
        """Return True when an exclude rule is a plain path-segment name."""
        return "/" not in rule and not any(ch in rule for ch in "*?[")

    def _join_rel_path(self, rel_root: str, name: str) -> str:
        """Join one relative root plus child name into a normalized POSIX path."""
        if not rel_root:
            return name.lower()
        return f"{rel_root}/{name}".lower()

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
        """Extract plain text from path via all2txt."""
        try:
            import all2txt.backends  # noqa: F401 — triggers backend registration
            from all2txt import registry
            from all2txt.core.config import Config as All2txtConfig
        except ImportError as exc:
            raise ImportError(
                "all2txt is required but not installed. "
                "Run 'uv sync' to install project dependencies."
            ) from exc

        if dir_cfg.extractor_config:
            cfg = All2txtConfig(**dir_cfg.extractor_config)
            registry.configure(cfg)
        return registry.extract(path)
