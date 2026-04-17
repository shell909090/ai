"""Tests for configuration loading."""

from pathlib import Path

import pytest

from elocate.config import (
    DEFAULT_EXTENSIONS,
    DEFAULT_EXTRACTORS,
    Config,
    DirConfig,
    load_config,
)


def test_default_config_values() -> None:
    config = Config()
    assert config.top_k == 10
    assert config.chunk_size == 500
    assert config.chunk_overlap == 50
    assert config.dirs == []


def test_default_dir_config_values() -> None:
    d = DirConfig(path="/tmp/docs")
    assert d.extensions == list(DEFAULT_EXTENSIONS)
    assert d.extractors == list(DEFAULT_EXTRACTORS)


def test_load_config_missing_file(tmp_path: Path) -> None:
    config = load_config(tmp_path / "nonexistent.yaml")
    assert isinstance(config, Config)
    assert config.top_k == 10
    assert config.dirs == []


def test_load_config_basic(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "top_k: 5\n"
        "embedding_model: my-model\n"
        "dirs:\n"
        "  - path: /docs\n"
        "    extensions: [.md]\n"
        "    extractors: [plaintext]\n"
    )
    config = load_config(cfg_file)
    assert config.top_k == 5
    assert config.embedding_model == "my-model"
    assert len(config.dirs) == 1
    assert config.dirs[0].path == "/docs"
    assert config.dirs[0].extensions == [".md"]


def test_load_config_index_path(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("index_path: /tmp/myindex\n")
    config = load_config(cfg_file)
    assert config.index_path == Path("/tmp/myindex")


def test_load_config_chunk_params(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("chunk_size: 300\nchunk_overlap: 30\n")
    config = load_config(cfg_file)
    assert config.chunk_size == 300
    assert config.chunk_overlap == 30
