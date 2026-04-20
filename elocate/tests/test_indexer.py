"""Tests for the Indexer module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from elocate.config import Config, DirConfig
from elocate.indexer import Indexer

DIM = 8


def _mock_embedder(dim: int = DIM) -> MagicMock:
    emb = MagicMock()
    emb.dim = dim
    emb.embed.side_effect = lambda texts: np.ones((len(texts), dim), dtype=np.float32)
    return emb


def _make_config(tmp_path: Path, dirs: list[DirConfig]) -> Config:
    return Config(
        dirs=dirs,
        index_path=tmp_path / "index",
        embedding_model="mock",
        chunk_size=500,
        chunk_overlap=50,
    )


@pytest.fixture
def notes_dir(tmp_path: Path) -> Path:
    d = tmp_path / "notes"
    d.mkdir()
    (d / "a.md").write_text(
        "First paragraph with real content.\n\nSecond paragraph with real content."
    )
    (d / "b.txt").write_text("Another document with sufficient content for indexing.")
    return d


def _make_indexer(tmp_path: Path, notes_dir: Path) -> tuple[Indexer, MagicMock]:
    cfg = _make_config(tmp_path, [DirConfig(path=str(notes_dir), extensions=[".md", ".txt"])])
    mock_emb = _mock_embedder()
    with patch("elocate.indexer.Embedder", return_value=mock_emb):
        indexer = Indexer(cfg)
    indexer._embedder_mock = mock_emb
    return indexer, mock_emb


def test_collect_files(tmp_path: Path, notes_dir: Path) -> None:
    cfg = _make_config(tmp_path, [DirConfig(path=str(notes_dir), extensions=[".md"])])
    indexer = Indexer(cfg)
    files = indexer._collect_files()
    assert len(files) == 1
    assert files[0][0].name == "a.md"


def test_collect_files_missing_dir(tmp_path: Path) -> None:
    cfg = _make_config(tmp_path, [DirConfig(path=str(tmp_path / "missing"), extensions=[".md"])])
    indexer = Indexer(cfg)
    files = indexer._collect_files()
    assert files == []


def test_collect_files_case_insensitive(tmp_path: Path) -> None:
    """Legacy extension rules should match case-insensitively."""
    d = tmp_path / "docs"
    d.mkdir()
    (d / "lower.md").write_text("lower content here for testing.")
    (d / "UPPER.MD").write_text("upper content here for testing.")
    cfg = _make_config(tmp_path, [DirConfig(path=str(d), extensions=[".md"])])
    indexer = Indexer(cfg)
    files = indexer._collect_files()
    names = {f.name for f, _ in files}
    assert "lower.md" in names
    assert "UPPER.MD" in names


def test_match_extension_rule_suffix(tmp_path: Path) -> None:
    cfg = _make_config(tmp_path, [])
    indexer = Indexer(cfg)
    assert indexer._match_extension_rule(Path("/tmp/archive.TAR.GZ"), "suffix:.tar.gz")
    assert not indexer._match_extension_rule(Path("/tmp/archive.gz"), "suffix:.tar.gz")


def test_match_extension_rule_glob(tmp_path: Path) -> None:
    cfg = _make_config(tmp_path, [])
    indexer = Indexer(cfg)
    assert indexer._match_extension_rule(Path("/tmp/Report.PDF"), "glob:*.pdf")
    assert not indexer._match_extension_rule(Path("/tmp/README"), "glob:*.*")


def test_collect_files_suffix_rule_matches_full_suffix(tmp_path: Path) -> None:
    d = tmp_path / "docs"
    d.mkdir()
    (d / "archive.tar.gz").write_text("archive payload with enough content.")
    (d / "single.gz").write_text("single payload with enough content.")
    cfg = _make_config(tmp_path, [DirConfig(path=str(d), extensions=["suffix:.tar.gz"])])
    indexer = Indexer(cfg)
    names = {f.name for f, _ in indexer._collect_files()}
    assert names == {"archive.tar.gz"}


def test_collect_files_glob_rule_matches_name(tmp_path: Path) -> None:
    d = tmp_path / "docs"
    d.mkdir()
    (d / "report.pdf").write_text("pdf payload with enough content.")
    (d / "README").write_text("readme payload with enough content.")
    cfg = _make_config(tmp_path, [DirConfig(path=str(d), extensions=["glob:*.*"])])
    indexer = Indexer(cfg)
    names = {f.name for f, _ in indexer._collect_files()}
    assert names == {"report.pdf"}


def test_collect_files_mixed_rules_are_ored(tmp_path: Path) -> None:
    d = tmp_path / "docs"
    d.mkdir()
    (d / "note.md").write_text("markdown payload with enough content.")
    (d / "bundle.tar.gz").write_text("archive payload with enough content.")
    (d / "README").write_text("readme payload with enough content.")
    cfg = _make_config(
        tmp_path,
        [DirConfig(path=str(d), extensions=[".md", "suffix:.tar.gz", "glob:read*"])],
    )
    indexer = Indexer(cfg)
    names = {f.name for f, _ in indexer._collect_files()}
    assert names == {"README", "bundle.tar.gz", "note.md"}


def test_collect_files_deduplicates_overlapping_dirs(tmp_path: Path) -> None:
    """B010: same file matched by two dir_cfg entries should appear only once."""
    d = tmp_path / "docs"
    d.mkdir()
    (d / "doc.md").write_text("Document content for dedup testing.")
    cfg = _make_config(
        tmp_path,
        [
            DirConfig(path=str(d), extensions=[".md"]),
            DirConfig(path=str(d), extensions=[".md"]),
        ],
    )
    indexer = Indexer(cfg)
    files = indexer._collect_files()
    assert len(files) == 1


def test_file_hash(tmp_path: Path) -> None:
    f = tmp_path / "test.txt"
    f.write_text("hello")
    cfg = _make_config(tmp_path, [])
    indexer = Indexer(cfg)
    h = indexer._file_hash(f)
    assert len(h) == 64  # SHA-256 hex


def test_file_hash_consistent(tmp_path: Path) -> None:
    f = tmp_path / "test.txt"
    f.write_text("same content")
    cfg = _make_config(tmp_path, [])
    indexer = Indexer(cfg)
    assert indexer._file_hash(f) == indexer._file_hash(f)


def test_extract_text_uses_all2txt_for_plaintext_files(tmp_path: Path) -> None:
    from all2txt import registry as _all2txt_registry

    f = tmp_path / "doc.md"
    f.write_text("Hello!")
    cfg = _make_config(tmp_path, [])
    indexer = Indexer(cfg)
    dir_cfg = DirConfig(path=str(tmp_path))
    with patch.object(_all2txt_registry, "extract", return_value="Hello!") as mock_extract:
        assert indexer._extract_text(f, dir_cfg) == "Hello!"
    mock_extract.assert_called_once_with(f)


def test_run_adds_new_files(tmp_path: Path, notes_dir: Path) -> None:
    cfg = _make_config(tmp_path, [DirConfig(path=str(notes_dir), extensions=[".md", ".txt"])])
    mock_emb = _mock_embedder()
    with patch("elocate.indexer.Embedder", return_value=mock_emb):
        indexer = Indexer(cfg)
        added, updated, removed = indexer.run()
    assert added == 2
    assert updated == 0
    assert removed == 0


def test_run_skips_unchanged_files(tmp_path: Path, notes_dir: Path) -> None:
    cfg = _make_config(tmp_path, [DirConfig(path=str(notes_dir), extensions=[".md", ".txt"])])
    mock_emb = _mock_embedder()
    with patch("elocate.indexer.Embedder", return_value=mock_emb):
        indexer = Indexer(cfg)
        indexer.run()
        added2, updated2, removed2 = indexer.run()
    assert added2 == 0
    assert updated2 == 0
    assert removed2 == 0


def test_run_detects_deleted_files(tmp_path: Path, notes_dir: Path) -> None:
    cfg = _make_config(tmp_path, [DirConfig(path=str(notes_dir), extensions=[".md"])])
    mock_emb = _mock_embedder()
    with patch("elocate.indexer.Embedder", return_value=mock_emb):
        indexer = Indexer(cfg)
        indexer.run()
        (notes_dir / "a.md").unlink()
        _, _, removed = indexer.run()
    assert removed == 1


def test_run_updates_changed_content(tmp_path: Path, notes_dir: Path) -> None:
    cfg = _make_config(tmp_path, [DirConfig(path=str(notes_dir), extensions=[".md"])])
    mock_emb = _mock_embedder()
    with patch("elocate.indexer.Embedder", return_value=mock_emb):
        indexer = Indexer(cfg)
        indexer.run()
        (notes_dir / "a.md").write_text("Completely new content here.")
        import time

        time.sleep(0.01)
        # force mtime change
        p = notes_dir / "a.md"
        p.touch()
        added, updated, removed = indexer.run()
    assert updated == 1


def test_run_dedup_hash(tmp_path: Path) -> None:
    """Duplicate file (same content) should not re-embed."""
    notes = tmp_path / "notes"
    notes.mkdir()
    content = "Shared content for dedup test."
    (notes / "orig.md").write_text(content)
    (notes / "copy.md").write_text(content)
    cfg = _make_config(tmp_path, [DirConfig(path=str(notes), extensions=[".md"])])
    mock_emb = _mock_embedder()
    with patch("elocate.indexer.Embedder", return_value=mock_emb):
        indexer = Indexer(cfg)
        indexer.run()
    # both paths in DB, but chunks only once
    db = indexer._db
    h = indexer._file_hash(notes / "orig.md")
    assert db.hash_has_chunks(h)
    paths = db.get_paths_by_hash(h)
    assert len(paths) == 2


def test_run_skips_small_files(tmp_path: Path) -> None:
    """B006: files smaller than MIN_FILE_BYTES must not be indexed."""
    notes = tmp_path / "notes"
    notes.mkdir()
    (notes / "tiny.md").write_bytes(b"ab")  # 2 bytes < MIN_FILE_BYTES
    (notes / "normal.md").write_text("Normal document with enough content.")
    cfg = _make_config(tmp_path, [DirConfig(path=str(notes), extensions=[".md"])])
    mock_emb = _mock_embedder()
    with patch("elocate.indexer.Embedder", return_value=mock_emb):
        indexer = Indexer(cfg)
        added, _, _ = indexer.run()
    assert added == 1
    assert indexer._db.get_file_meta(str(notes / "tiny.md")) is None
    assert indexer._db.get_file_meta(str(notes / "normal.md")) is not None


def test_run_batch_single_embed_call(tmp_path: Path) -> None:
    """B008: _index_batch must call embedder.embed exactly once per batch."""
    notes = tmp_path / "notes"
    notes.mkdir()
    for i in range(3):
        (notes / f"doc{i}.md").write_text(f"Document {i} with some content for testing.")
    cfg = _make_config(tmp_path, [DirConfig(path=str(notes), extensions=[".md"])])
    mock_emb = _mock_embedder()
    with patch("elocate.indexer.Embedder", return_value=mock_emb):
        indexer = Indexer(cfg)
        indexer.run()
    # All 3 files fit in one batch; embed should be called once
    assert mock_emb.embed.call_count == 1


def test_run_preserves_index_on_extract_failure(tmp_path: Path) -> None:
    """B001: extraction failure after content change must not destroy the old index."""
    notes = tmp_path / "notes"
    notes.mkdir()
    doc = notes / "doc.md"
    doc.write_text("Original content that was indexed successfully.")

    cfg = _make_config(tmp_path, [DirConfig(path=str(notes), extensions=[".md"])])
    mock_emb = _mock_embedder()
    with patch("elocate.indexer.Embedder", return_value=mock_emb):
        indexer = Indexer(cfg)
        indexer.run()

    db = indexer._db
    path_str = str(doc)
    old_meta = db.get_file_meta(path_str)
    assert old_meta is not None
    old_hash = old_meta["file_hash"]
    assert db.hash_has_chunks(old_hash)

    # Change content so the file gets a new hash and triggers re-processing
    doc.write_text("Updated content that will fail extraction — different size.")

    with patch("elocate.indexer.Embedder", return_value=mock_emb):
        with patch.object(indexer, "_extract_text", side_effect=RuntimeError("disk error")):
            indexer.run()

    # Old index must still be intact
    meta = db.get_file_meta(path_str)
    assert meta is not None
    assert meta["file_hash"] == old_hash
    assert db.hash_has_chunks(old_hash)


def test_run_rebuilds_on_model_change(tmp_path: Path, notes_dir: Path) -> None:
    """B002: switching embedding_model must force a full index rebuild."""
    cfg_a = Config(
        dirs=[DirConfig(path=str(notes_dir), extensions=[".md", ".txt"])],
        index_path=tmp_path / "index",
        embedding_model="model-a",
        chunk_size=500,
        chunk_overlap=50,
    )
    mock_emb = _mock_embedder()
    with patch("elocate.indexer.Embedder", return_value=mock_emb):
        indexer_a = Indexer(cfg_a)
        added_a, _, _ = indexer_a.run()
    assert added_a == 2

    cfg_b = Config(
        dirs=[DirConfig(path=str(notes_dir), extensions=[".md", ".txt"])],
        index_path=tmp_path / "index",
        embedding_model="model-b",
        chunk_size=500,
        chunk_overlap=50,
    )
    with patch("elocate.indexer.Embedder", return_value=mock_emb):
        indexer_b = Indexer(cfg_b)
        added_b, updated_b, _ = indexer_b.run()

    # After rebuild all files are new again
    assert added_b == 2
    assert updated_b == 0


def test_run_no_infinite_reprocess_for_no_chunk_file(tmp_path: Path) -> None:
    """Files that produce no chunks must still be recorded in file_meta so they are
    not re-processed on every subsequent run."""
    notes = tmp_path / "notes"
    notes.mkdir()
    # Content is ≥ MIN_FILE_BYTES but every line < MIN_CHUNK_CHARS (20) → no chunks
    (notes / "tiny.md").write_text("hi\n\nok\n\nyes")
    cfg = _make_config(tmp_path, [DirConfig(path=str(notes), extensions=[".md"])])
    mock_emb = _mock_embedder()

    with patch("elocate.indexer.Embedder", return_value=mock_emb):
        indexer = Indexer(cfg)
        added1, _, _ = indexer.run()
        added2, updated2, _ = indexer.run()

    assert added1 == 1
    # Second run must not re-process the same file
    assert added2 == 0
    assert updated2 == 0


def test_extract_text_all2txt_success(tmp_path: Path) -> None:
    from all2txt import registry as _all2txt_registry

    f = tmp_path / "doc.pdf"
    f.write_text("dummy")
    cfg = _make_config(tmp_path, [])
    indexer = Indexer(cfg)
    dir_cfg = DirConfig(path=str(tmp_path), extractor_config={})
    with (
        patch.object(_all2txt_registry, "extract", return_value="mocked text") as mock_extract,
        patch.object(_all2txt_registry, "configure") as mock_configure,
    ):
        result = indexer._extract_text(f, dir_cfg)
    assert result == "mocked text"
    mock_extract.assert_called_once_with(f)
    mock_configure.assert_not_called()


def test_extract_text_all2txt_with_config(tmp_path: Path) -> None:
    from all2txt import registry as _all2txt_registry

    f = tmp_path / "doc.pdf"
    f.write_text("dummy")
    cfg = _make_config(tmp_path, [])
    indexer = Indexer(cfg)
    extractor_config = {"backends": {}, "extractors": {}, "extensions": {}}
    dir_cfg = DirConfig(path=str(tmp_path), extractor_config=extractor_config)
    with (
        patch.object(_all2txt_registry, "extract", return_value="configured text") as mock_extract,
        patch.object(_all2txt_registry, "configure") as mock_configure,
    ):
        result = indexer._extract_text(f, dir_cfg)
    assert result == "configured text"
    mock_configure.assert_called_once()
    mock_extract.assert_called_once_with(f)


def test_extract_text_all2txt_import_error(tmp_path: Path) -> None:
    f = tmp_path / "doc.pdf"
    f.write_text("dummy")
    cfg = _make_config(tmp_path, [])
    indexer = Indexer(cfg)
    dir_cfg = DirConfig(path=str(tmp_path))
    with patch.dict("sys.modules", {"all2txt.backends": None}):
        with pytest.raises(ImportError):
            indexer._extract_text(f, dir_cfg)
