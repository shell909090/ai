"""Unit tests for all2txt.core.config.load_config()."""
from pathlib import Path

from all2txt.core.config import Config, load_config

# ---------------------------------------------------------------------------
# 1. No file present → empty Config
# ---------------------------------------------------------------------------


def test_load_config_missing_file(tmp_path: Path) -> None:
    config = load_config(tmp_path / "nonexistent.yaml")

    assert isinstance(config, Config)
    assert config.backends == {}
    assert config.extractors == {}
    assert config.extensions == {}


# ---------------------------------------------------------------------------
# 2. Valid YAML → correct backends / extractors / extensions
# ---------------------------------------------------------------------------


def test_load_config_valid_yaml(tmp_path: Path) -> None:
    yaml_text = """\
mime:
  application/pdf:
    backends:
      - pymupdf
      - tika
  text/html:
    backends:
      - pandoc

extractor:
  pymupdf:
    dpi: 150
  tika:
    server_url: http://localhost:9998

extensions:
  .rst: text/x-rst
  .adoc: text/x-asciidoc
"""
    cfg_file = tmp_path / "all2txt.yaml"
    cfg_file.write_text(yaml_text)

    config = load_config(cfg_file)

    assert config.backends == {
        "application/pdf": ["pymupdf", "tika"],
        "text/html": ["pandoc"],
    }
    assert config.extractors == {
        "pymupdf": {"dpi": 150},
        "tika": {"server_url": "http://localhost:9998"},
    }
    assert config.extensions == {
        ".rst": "text/x-rst",
        ".adoc": "text/x-asciidoc",
    }


# ---------------------------------------------------------------------------
# 3. Empty YAML file → empty Config
# ---------------------------------------------------------------------------


def test_load_config_empty_yaml(tmp_path: Path) -> None:
    cfg_file = tmp_path / "all2txt.yaml"
    cfg_file.write_text("")

    config = load_config(cfg_file)

    assert isinstance(config, Config)
    assert config.backends == {}
    assert config.extractors == {}
    assert config.extensions == {}


# ---------------------------------------------------------------------------
# 4. Partial YAML → valid Config with defaults for missing fields
# ---------------------------------------------------------------------------


def test_load_config_partial_yaml_only_extensions(tmp_path: Path) -> None:
    yaml_text = """\
extensions:
  .md: text/markdown
"""
    cfg_file = tmp_path / "all2txt.yaml"
    cfg_file.write_text(yaml_text)

    config = load_config(cfg_file)

    assert config.extensions == {".md": "text/markdown"}
    # Missing fields get their dataclass defaults.
    assert config.backends == {}
    assert config.extractors == {}


def test_load_config_partial_yaml_only_mime(tmp_path: Path) -> None:
    yaml_text = """\
mime:
  application/pdf:
    backends:
      - pymupdf
"""
    cfg_file = tmp_path / "all2txt.yaml"
    cfg_file.write_text(yaml_text)

    config = load_config(cfg_file)

    assert config.backends == {"application/pdf": ["pymupdf"]}
    assert config.extractors == {}
    assert config.extensions == {}


def test_load_config_partial_yaml_only_extractor(tmp_path: Path) -> None:
    yaml_text = """\
extractor:
  tika:
    server_url: http://tika:9998
"""
    cfg_file = tmp_path / "all2txt.yaml"
    cfg_file.write_text(yaml_text)

    config = load_config(cfg_file)

    assert config.extractors == {"tika": {"server_url": "http://tika:9998"}}
    assert config.backends == {}
    assert config.extensions == {}


def test_load_config_mime_entry_without_backends_key(tmp_path: Path) -> None:
    """A MIME section with no 'backends' key should map to an empty list."""
    yaml_text = """\
mime:
  application/pdf: {}
"""
    cfg_file = tmp_path / "all2txt.yaml"
    cfg_file.write_text(yaml_text)

    config = load_config(cfg_file)

    assert config.backends == {"application/pdf": []}
