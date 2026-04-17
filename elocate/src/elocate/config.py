"""Configuration loading and validation."""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "elocate" / "config.toml"
DEFAULT_INDEX_PATH = Path.home() / ".local" / "share" / "elocate" / "index"
DEFAULT_EXTENSIONS = [".md", ".txt", ".rst", ".org"]
DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"


@dataclass
class Config:
    """Application configuration."""

    index_dirs: list[str] = field(default_factory=list)
    index_path: Path = field(default_factory=lambda: DEFAULT_INDEX_PATH)
    file_extensions: list[str] = field(default_factory=lambda: list(DEFAULT_EXTENSIONS))
    top_k: int = 10
    embedding_model: str = DEFAULT_EMBEDDING_MODEL


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> Config:
    """Load configuration from TOML file, falling back to defaults."""
    if not path.exists():
        return Config()
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return Config(
        index_dirs=data.get("index_dirs", []),
        index_path=Path(data.get("index_path", str(DEFAULT_INDEX_PATH))),
        file_extensions=data.get("file_extensions", list(DEFAULT_EXTENSIONS)),
        top_k=data.get("top_k", 10),
        embedding_model=data.get("embedding_model", DEFAULT_EMBEDDING_MODEL),
    )
