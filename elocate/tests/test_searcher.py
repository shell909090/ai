"""Tests for Searcher."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from elocate.config import Config, DirConfig
from elocate.searcher import Searcher, SearchResult

DIM = 8


def _make_config(tmp_path: Path) -> Config:
    return Config(
        dirs=[DirConfig(path=str(tmp_path / "docs"), extensions=[".md"])],
        index_path=tmp_path / "index",
        embedding_model="mock",
        top_k=5,
    )


def _mock_embedder(dim: int = DIM) -> MagicMock:
    emb = MagicMock()
    emb.dim = dim
    emb.embed.side_effect = lambda texts: np.ones((len(texts), dim), dtype=np.float32)
    return emb


def test_search_raises_if_no_index(tmp_path: Path) -> None:
    cfg = _make_config(tmp_path)
    searcher = Searcher(cfg)
    with pytest.raises(RuntimeError, match="elocate-updatedb"):
        searcher.search("hello")


_DEFAULT_CONTENT = "Hello world with enough content to index."


def _build_index(tmp_path: Path, cfg: Config, content: str = _DEFAULT_CONTENT) -> None:
    from elocate.indexer import Indexer

    docs = tmp_path / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "doc.md").write_text(content)
    mock_emb = _mock_embedder()
    with patch("elocate.indexer.Embedder", return_value=mock_emb):
        Indexer(cfg).run()


def test_search_returns_results(tmp_path: Path) -> None:
    cfg = _make_config(tmp_path)
    _build_index(tmp_path, cfg)
    mock_emb = _mock_embedder()
    with patch("elocate.searcher.Embedder", return_value=mock_emb):
        searcher = Searcher(cfg)
        results = searcher.search("hello")
    assert len(results) > 0
    assert isinstance(results[0], SearchResult)


def test_search_score_in_range(tmp_path: Path) -> None:
    cfg = _make_config(tmp_path)
    _build_index(tmp_path, cfg)
    mock_emb = _mock_embedder()
    with patch("elocate.searcher.Embedder", return_value=mock_emb):
        results = Searcher(cfg).search("hello")
    for r in results:
        assert -1.0 <= r.score <= 1.0


def test_search_snippet_max_200(tmp_path: Path) -> None:
    cfg = _make_config(tmp_path)
    _build_index(tmp_path, cfg, content="A" * 500)
    mock_emb = _mock_embedder()
    with patch("elocate.searcher.Embedder", return_value=mock_emb):
        results = Searcher(cfg).search("AAAA")
    for r in results:
        assert len(r.snippet) <= 200


def test_search_results_sorted_by_score(tmp_path: Path) -> None:
    cfg = _make_config(tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir(exist_ok=True)
    for i in range(3):
        (docs / f"doc{i}.md").write_text(f"Document number {i} with content.")
    mock_emb = _mock_embedder()
    with patch("elocate.indexer.Embedder", return_value=mock_emb):
        from elocate.indexer import Indexer

        Indexer(cfg).run()
    with patch("elocate.searcher.Embedder", return_value=mock_emb):
        results = Searcher(cfg).search("document")
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_search_regex_filter(tmp_path: Path) -> None:
    cfg = _make_config(tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "match.md").write_text("This has special content.")
    (docs / "other.md").write_text("This has other content.")
    mock_emb = _mock_embedder()
    with patch("elocate.indexer.Embedder", return_value=mock_emb):
        from elocate.indexer import Indexer

        Indexer(cfg).run()
    with patch("elocate.searcher.Embedder", return_value=mock_emb):
        results = Searcher(cfg).search("content", pattern="match")
    assert all("match" in p for r in results for p in r.paths)


def test_search_paths_contains_all_hash_paths(tmp_path: Path) -> None:
    cfg = _make_config(tmp_path)
    _build_index(tmp_path, cfg)
    mock_emb = _mock_embedder()
    with patch("elocate.searcher.Embedder", return_value=mock_emb):
        results = Searcher(cfg).search("hello")
    assert len(results) > 0
    assert isinstance(results[0].paths, list)
    assert len(results[0].paths) >= 1
