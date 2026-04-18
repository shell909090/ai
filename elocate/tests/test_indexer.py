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
    (d / "a.md").write_text("Hello world\n\nSecond paragraph.")
    (d / "b.txt").write_text("Another document.")
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


def test_extract_text_plaintext(tmp_path: Path) -> None:
    f = tmp_path / "doc.md"
    f.write_text("Hello!")
    cfg = _make_config(tmp_path, [])
    indexer = Indexer(cfg)
    dir_cfg = DirConfig(path=str(tmp_path), extractor="plaintext")
    assert indexer._extract_text(f, dir_cfg) == "Hello!"


def test_extract_text_unknown_extractor(tmp_path: Path) -> None:
    f = tmp_path / "doc.md"
    f.write_text("x")
    cfg = _make_config(tmp_path, [])
    indexer = Indexer(cfg)
    dir_cfg = DirConfig(path=str(tmp_path), extractor="unknown")
    with pytest.raises(ValueError):
        indexer._extract_text(f, dir_cfg)


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
