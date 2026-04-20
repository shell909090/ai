"""Tests for configuration loading."""

from pathlib import Path

import pytest

from elocate.config import (
    DEFAULT_EXTENSIONS,
    Config,
    DirConfig,
    load_config,
    validate_extension_rule,
)


def test_default_config_values() -> None:
    config = Config()
    assert config.top_k == 10
    assert config.chunk_size == 500
    assert config.chunk_overlap == 50
    assert config.dirs == []


def test_default_dir_config() -> None:
    d = DirConfig(path="/tmp/docs")
    assert d.extensions == list(DEFAULT_EXTENSIONS)
    assert d.extractor == "plaintext"
    assert d.extractor_config == {}


def test_validate_extension_rule_legacy_extension() -> None:
    assert validate_extension_rule(".MD") == ".md"


def test_validate_extension_rule_suffix() -> None:
    assert validate_extension_rule("suffix:.Tar.Gz") == "suffix:.tar.gz"


def test_validate_extension_rule_glob() -> None:
    assert validate_extension_rule("glob:*.*") == "glob:*.*"


def test_load_config_missing_file(tmp_path: Path) -> None:
    config = load_config(tmp_path / "nonexistent.yaml")
    assert isinstance(config, Config)
    assert config.top_k == 10
    assert config.dirs == []


def test_load_config_global_fields(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("top_k: 5\nembedding_model: my-model\nchunk_size: 300\nchunk_overlap: 30\n")
    config = load_config(cfg_file)
    assert config.top_k == 5
    assert config.embedding_model == "my-model"
    assert config.chunk_size == 300
    assert config.chunk_overlap == 30


def test_load_config_dirs(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "dirs:\n"
        "  - path: /docs\n"
        "    extensions: [.md, suffix:.tar.gz, glob:*.*]\n"
        "    extractor: plaintext\n"
    )
    config = load_config(cfg_file)
    assert len(config.dirs) == 1
    assert config.dirs[0].path == "/docs"
    assert config.dirs[0].extensions == [".md", "suffix:.tar.gz", "glob:*.*"]
    assert config.dirs[0].extractor == "plaintext"


def test_load_config_all2txt_extractor(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "dirs:\n"
        "  - path: /photos\n"
        "    extensions: [.jpg]\n"
        "    extractor: all2txt\n"
        "    extractor_config:\n"
        "      mime:\n"
        '        "image/jpeg":\n'
        "          backends: [openai_vision]\n"
        "      extractor:\n"
        "        openai_vision:\n"
        "          model: gpt-4o\n"
    )
    config = load_config(cfg_file)
    d = config.dirs[0]
    assert d.extractor == "all2txt"
    assert d.extractor_config["mime"]["image/jpeg"]["backends"] == ["openai_vision"]
    assert d.extractor_config["extractor"]["openai_vision"]["model"] == "gpt-4o"


def test_load_config_index_path(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("index_path: /tmp/myindex\n")
    config = load_config(cfg_file)
    assert config.index_path == Path("/tmp/myindex")


def test_load_config_openai_fields(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "embedding_model: nomic-embed-text\n"
        "openai_base_url: http://localhost:11434/v1\n"
        "openai_api_key: ollama\n"
    )
    config = load_config(cfg_file)
    assert config.embedding_model == "nomic-embed-text"
    assert config.openai_base_url == "http://localhost:11434/v1"
    assert config.openai_api_key == "ollama"


def test_load_config_index_path_tilde_expansion(tmp_path: Path) -> None:
    """B003: index_path with ~ must be expanded to an absolute path."""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("index_path: ~/elocate-test-index\n")
    config = load_config(cfg_file)
    assert not str(config.index_path).startswith("~")
    assert config.index_path.is_absolute()


# ---- B009: config validation ----


def test_load_config_invalid_top_k(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("top_k: 0\n")
    with pytest.raises(ValueError, match="top_k"):
        load_config(cfg_file)


def test_load_config_invalid_chunk_size(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("chunk_size: -1\n")
    with pytest.raises(ValueError, match="chunk_size"):
        load_config(cfg_file)


def test_load_config_invalid_chunk_overlap_negative(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("chunk_overlap: -1\n")
    with pytest.raises(ValueError, match="chunk_overlap"):
        load_config(cfg_file)


def test_load_config_invalid_chunk_overlap_gte_size(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("chunk_size: 100\nchunk_overlap: 100\n")
    with pytest.raises(ValueError, match="chunk_overlap"):
        load_config(cfg_file)


def test_load_config_local_backend_raises(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("embedder_backend: local\n")
    with pytest.raises(ValueError, match="local"):
        load_config(cfg_file)


def test_load_config_missing_dir_path(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("dirs:\n  - extensions: [.md]\n")
    with pytest.raises(ValueError, match="dirs\\[0\\]"):
        load_config(cfg_file)


def test_load_config_invalid_extension_prefix(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("dirs:\n  - path: /docs\n    extensions: [magic:.md]\n")
    with pytest.raises(ValueError, match="unknown extension rule prefix"):
        load_config(cfg_file)


def test_load_config_invalid_suffix_rule(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("dirs:\n  - path: /docs\n    extensions: [suffix:tar.gz]\n")
    with pytest.raises(ValueError, match="suffix"):
        load_config(cfg_file)


def test_load_config_invalid_glob_rule(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text('dirs:\n  - path: /docs\n    extensions: ["glob:"]\n')
    with pytest.raises(ValueError, match="glob"):
        load_config(cfg_file)
