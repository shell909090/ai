"""Tests for configuration loading."""

from pathlib import Path

from elocate.config import (
    DEFAULT_EXTENSIONS,
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


def test_default_dir_config() -> None:
    d = DirConfig(path="/tmp/docs")
    assert d.extensions == list(DEFAULT_EXTENSIONS)
    assert d.extractor == "plaintext"
    assert d.extractor_config == {}


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
        "dirs:\n  - path: /docs\n    extensions: [.md, .txt]\n    extractor: plaintext\n"
    )
    config = load_config(cfg_file)
    assert len(config.dirs) == 1
    assert config.dirs[0].path == "/docs"
    assert config.dirs[0].extensions == [".md", ".txt"]
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
