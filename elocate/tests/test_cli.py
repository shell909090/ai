"""Integration tests for CLI commands."""

from pathlib import Path
from unittest.mock import patch

import numpy as np
from click.testing import CliRunner

from elocate.cli import main_search, main_updatedb
from elocate.config import Config, DirConfig

DIM = 8


def _mock_embedder(dim: int = DIM):  # type: ignore[return]
    from unittest.mock import MagicMock

    emb = MagicMock()
    emb.dim = dim
    emb.embed.side_effect = lambda texts: np.ones((len(texts), dim), dtype=np.float32)
    return emb


def _default_config(tmp_path: Path, has_docs: bool = True) -> Config:
    docs = tmp_path / "docs"
    if has_docs:
        docs.mkdir(exist_ok=True)
        (docs / "note.md").write_text("Hello semantic search world.")
    return Config(
        dirs=[DirConfig(path=str(docs), extensions=[".md"])] if has_docs else [],
        index_path=tmp_path / "index",
        embedding_model="mock",
        top_k=5,
    )


def test_updatedb_no_dirs(tmp_path: Path) -> None:
    runner = CliRunner()
    cfg = _default_config(tmp_path, has_docs=False)
    with patch("elocate.cli.load_config", return_value=cfg):
        result = runner.invoke(main_updatedb, [])
    assert result.exit_code == 1
    assert "no dirs" in result.output.lower() or "warning" in result.output.lower()


def test_updatedb_success(tmp_path: Path) -> None:
    runner = CliRunner()
    cfg = _default_config(tmp_path)
    mock_emb = _mock_embedder()
    with patch("elocate.cli.load_config", return_value=cfg):
        with patch("elocate.indexer.Embedder", return_value=mock_emb):
            result = runner.invoke(main_updatedb, [])
    assert result.exit_code == 0
    assert "Done:" in result.output
    assert "added" in result.output


def test_search_no_index(tmp_path: Path) -> None:
    runner = CliRunner()
    cfg = _default_config(tmp_path)
    with patch("elocate.cli.load_config", return_value=cfg):
        result = runner.invoke(main_search, ["hello"])
    assert result.exit_code == 1
    assert "elocate-updatedb" in result.output


def test_search_invalid_regex(tmp_path: Path) -> None:
    runner = CliRunner()
    cfg = _default_config(tmp_path)
    mock_emb = _mock_embedder()
    with patch("elocate.cli.load_config", return_value=cfg):
        with patch("elocate.indexer.Embedder", return_value=mock_emb):
            runner.invoke(main_updatedb, [])
        with patch("elocate.searcher.Embedder", return_value=mock_emb):
            result = runner.invoke(main_search, ["hello", "-p", "[invalid"])
    assert result.exit_code == 1
    assert "regex" in result.output.lower() or "pattern" in result.output.lower()


def test_full_updatedb_then_search(tmp_path: Path) -> None:
    """Integration: updatedb followed by search returns results."""
    runner = CliRunner()
    cfg = _default_config(tmp_path)
    mock_emb = _mock_embedder()
    with patch("elocate.cli.load_config", return_value=cfg):
        with patch("elocate.indexer.Embedder", return_value=mock_emb):
            update_result = runner.invoke(main_updatedb, [])
        assert update_result.exit_code == 0

        with patch("elocate.searcher.Embedder", return_value=mock_emb):
            search_result = runner.invoke(main_search, ["hello"])
    assert search_result.exit_code == 0
    assert "note.md" in search_result.output


def test_search_with_regex_filter(tmp_path: Path) -> None:
    runner = CliRunner()
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "match.md").write_text("Hello match content.")
    (docs / "other.md").write_text("Hello other content.")
    cfg = Config(
        dirs=[DirConfig(path=str(docs), extensions=[".md"])],
        index_path=tmp_path / "index",
        embedding_model="mock",
        top_k=10,
    )
    mock_emb = _mock_embedder()
    with patch("elocate.cli.load_config", return_value=cfg):
        with patch("elocate.indexer.Embedder", return_value=mock_emb):
            runner.invoke(main_updatedb, [])
        with patch("elocate.searcher.Embedder", return_value=mock_emb):
            result = runner.invoke(main_search, ["hello", "-p", "match"])
    assert result.exit_code == 0
    assert "match.md" in result.output


def test_updatedb_value_error(tmp_path: Path) -> None:
    """B004: ValueError during indexing must produce a friendly error and exit 1."""
    runner = CliRunner()
    cfg = _default_config(tmp_path)
    with patch("elocate.cli.load_config", return_value=cfg):
        with patch("elocate.indexer.Embedder", side_effect=ValueError("unknown backend: bad")):
            result = runner.invoke(main_updatedb, [])
    assert result.exit_code == 1
    assert "Error:" in result.output


def test_search_import_error(tmp_path: Path) -> None:
    """B004: ImportError during search must produce a friendly error and exit 1."""
    runner = CliRunner()
    cfg = _default_config(tmp_path)
    mock_emb = _mock_embedder()
    with patch("elocate.cli.load_config", return_value=cfg):
        with patch("elocate.indexer.Embedder", return_value=mock_emb):
            runner.invoke(main_updatedb, [])
        with patch("elocate.searcher.Embedder", side_effect=ImportError("openai not installed")):
            result = runner.invoke(main_search, ["hello"])
    assert result.exit_code == 1
    assert "Error:" in result.output
