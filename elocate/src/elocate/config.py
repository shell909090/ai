"""Configuration loading and validation."""

from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "elocate" / "config.yaml"
DEFAULT_INDEX_PATH = Path.home() / ".local" / "share" / "elocate" / "index"
DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
DEFAULT_EXTENSIONS = [".md", ".txt", ".rst", ".org"]
DEFAULT_EXTRACTORS = ["plaintext"]


@dataclass
class DirConfig:
    """Per-directory indexing configuration."""

    path: str
    extensions: list[str] = field(default_factory=lambda: list(DEFAULT_EXTENSIONS))
    extractors: list[str] = field(default_factory=lambda: list(DEFAULT_EXTRACTORS))


@dataclass
class Config:
    """Application configuration."""

    dirs: list[DirConfig] = field(default_factory=list)
    index_path: Path = field(default_factory=lambda: DEFAULT_INDEX_PATH)
    top_k: int = 10
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    chunk_size: int = 500
    chunk_overlap: int = 50


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> Config:
    """Load configuration from YAML file, falling back to defaults."""
    raise NotImplementedError
