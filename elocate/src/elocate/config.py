"""Configuration loading and validation."""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "elocate" / "config.yaml"
DEFAULT_INDEX_PATH = Path.home() / ".local" / "share" / "elocate" / "index"
DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"
DEFAULT_EXTENSIONS = [".md", ".txt", ".rst", ".org"]


@dataclass
class DirConfig:
    """Per-directory indexing configuration."""

    path: str
    extensions: list[str] = field(default_factory=lambda: list(DEFAULT_EXTENSIONS))
    extractor: str = "plaintext"  # "plaintext" | "all2txt"
    extractor_config: dict[str, Any] = field(default_factory=dict)
    # extractor_config is forwarded to all2txt.Config when extractor="all2txt";
    # keys mirror all2txt's YAML format: mime / extractor / extensions.


@dataclass
class Config:
    """Application configuration."""

    dirs: list[DirConfig] = field(default_factory=list)
    index_path: Path = field(default_factory=lambda: DEFAULT_INDEX_PATH)
    top_k: int = 10
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    chunk_size: int = 500
    chunk_overlap: int = 50
    openai_base_url: str = ""  # OpenAI-compatible API base URL
    openai_api_key: str = ""  # API key (empty = use "none")


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> Config:
    """Load configuration from YAML file, falling back to defaults."""
    if not path.exists():
        logger.debug("Config file not found at %s, using defaults", path)
        return Config()

    with path.open() as f:
        data = yaml.safe_load(f) or {}

    if data.get("embedder_backend") == "local":
        raise ValueError(
            "The 'local' embedder backend has been removed. "
            "Use an OpenAI-compatible service (ollama, OpenAI, etc.) and set openai_base_url."
        )

    dirs: list[DirConfig] = []
    for i, entry in enumerate(data.get("dirs", [])):
        if "path" not in entry:
            raise ValueError(f"dirs[{i}] is missing required field 'path'")
        dirs.append(
            DirConfig(
                path=entry["path"],
                extensions=entry.get("extensions", list(DEFAULT_EXTENSIONS)),
                extractor=entry.get("extractor", "plaintext"),
                extractor_config=entry.get("extractor_config", {}),
            )
        )

    index_path_raw = data.get("index_path")
    index_path = Path(index_path_raw).expanduser() if index_path_raw else DEFAULT_INDEX_PATH

    top_k = data.get("top_k", 10)
    chunk_size = data.get("chunk_size", 500)
    chunk_overlap = data.get("chunk_overlap", 50)

    if top_k <= 0:
        raise ValueError(f"top_k must be > 0, got {top_k}")
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be > 0, got {chunk_size}")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError(
            f"chunk_overlap must be in [0, chunk_size), "
            f"got overlap={chunk_overlap} size={chunk_size}"
        )

    return Config(
        dirs=dirs,
        index_path=index_path,
        top_k=top_k,
        embedding_model=data.get("embedding_model", DEFAULT_EMBEDDING_MODEL),
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        openai_base_url=data.get("openai_base_url", ""),
        openai_api_key=data.get("openai_api_key", ""),
    )
