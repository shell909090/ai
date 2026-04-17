"""Tests for configuration loading."""

from pathlib import Path

from elocate.config import (
    DEFAULT_EXTENSIONS,
    Config,
    load_config,
)


def test_default_config_values() -> None:
    config = Config()
    assert config.top_k == 10
    assert config.index_dirs == []
    assert config.file_extensions == list(DEFAULT_EXTENSIONS)


def test_load_config_missing_file(tmp_path: Path) -> None:
    config = load_config(tmp_path / "nonexistent.toml")
    assert isinstance(config, Config)
    assert config.top_k == 10
    assert ".md" in config.file_extensions


def test_load_config_from_toml(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_bytes(
        b'top_k = 5\nindex_dirs = ["/docs"]\nembedding_model = "my-model"\n'
    )
    config = load_config(cfg_file)
    assert config.top_k == 5
    assert "/docs" in config.index_dirs
    assert config.embedding_model == "my-model"


def test_load_config_index_path(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_bytes(b'index_path = "/tmp/myindex"\n')
    config = load_config(cfg_file)
    assert config.index_path == Path("/tmp/myindex")
