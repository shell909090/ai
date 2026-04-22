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
DEFAULT_SUMMARY_MODEL = "qwen3.5:4b"
DEFAULT_EXTENSIONS = [".md", ".txt", ".rst", ".org"]
DEFAULT_CHUNK_SIZE = 2048
DEFAULT_CHUNK_OVERLAP = 200
DEFAULT_EMBED_BATCH_FILES = 64
DEFAULT_EMBED_BATCH_CHARS = 65536
DEFAULT_RAG_ENTROPY_MIN = 4.5
DEFAULT_RAG_ENTROPY_MAX = 8.8
DEFAULT_RAG_MIN_PARAGRAPH_LENGTH = 80
_EXTENSION_RULE_PREFIXES = frozenset({"suffix", "glob"})


@dataclass
class DirConfig:
    """Per-directory indexing configuration."""

    path: str
    extensions: list[str] = field(default_factory=lambda: list(DEFAULT_EXTENSIONS))
    exclude: list[str] = field(default_factory=list)
    extractor_config: dict[str, Any] = field(default_factory=dict)
    # extractor_config is forwarded to all2txt.Config;
    # supported top-level keys are: backends / extractors / extensions.


@dataclass
class Config:
    """Application configuration."""

    dirs: list[DirConfig] = field(default_factory=list)
    index_path: Path = field(default_factory=lambda: DEFAULT_INDEX_PATH)
    top_k: int = 10
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    summary_model: str = DEFAULT_SUMMARY_MODEL
    chunk_size: int = DEFAULT_CHUNK_SIZE
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP
    embed_batch_files: int = DEFAULT_EMBED_BATCH_FILES
    embed_batch_chars: int = DEFAULT_EMBED_BATCH_CHARS
    rag_entropy_min: float = DEFAULT_RAG_ENTROPY_MIN
    rag_entropy_max: float = DEFAULT_RAG_ENTROPY_MAX
    rag_min_paragraph_length: int = DEFAULT_RAG_MIN_PARAGRAPH_LENGTH
    openai_base_url: str = ""  # OpenAI-compatible API base URL
    openai_api_key: str = ""  # API key (empty = use "none")


def validate_extension_rule(rule: str) -> str:
    """Validate one extension rule and return its normalized form."""
    if not isinstance(rule, str):
        raise ValueError(f"extension rule must be a string, got {type(rule).__name__}")

    normalized = rule.strip().lower()
    if not normalized:
        raise ValueError("extension rule must not be empty")

    prefix, sep, value = normalized.partition(":")
    if sep:
        if prefix not in _EXTENSION_RULE_PREFIXES:
            raise ValueError(f"unknown extension rule prefix: {prefix}")
        if not value:
            raise ValueError(f"{prefix}: rule must not be empty")
        if prefix == "suffix" and not value.startswith("."):
            raise ValueError("suffix: rules must start with '.'")
        return f"{prefix}:{value}"

    if not normalized.startswith("."):
        raise ValueError("extension rules without a prefix must start with '.'")
    return normalized


def validate_exclude_rule(rule: str) -> str:
    """Validate one exclude rule and return its normalized form."""
    if not isinstance(rule, str):
        raise ValueError(f"exclude rule must be a string, got {type(rule).__name__}")

    normalized = rule.strip().replace("\\", "/").lower()
    if not normalized:
        raise ValueError("exclude rule must not be empty")

    return normalized


def _load_scalar_config(data: dict[str, Any]) -> dict[str, Any]:
    """Parse and validate scalar top-level config values."""
    index_path_raw = data.get("index_path")
    index_path = Path(index_path_raw).expanduser() if index_path_raw else DEFAULT_INDEX_PATH

    top_k = data.get("top_k", 10)
    chunk_size = data.get("chunk_size", DEFAULT_CHUNK_SIZE)
    chunk_overlap = data.get("chunk_overlap", DEFAULT_CHUNK_OVERLAP)
    embed_batch_files = data.get("embed_batch_files", DEFAULT_EMBED_BATCH_FILES)
    embed_batch_chars = data.get("embed_batch_chars", DEFAULT_EMBED_BATCH_CHARS)
    summary_model = data.get("summary_model", DEFAULT_SUMMARY_MODEL)
    rag_entropy_min = data.get("rag_entropy_min", DEFAULT_RAG_ENTROPY_MIN)
    rag_entropy_max = data.get("rag_entropy_max", DEFAULT_RAG_ENTROPY_MAX)
    rag_min_paragraph_length = data.get(
        "rag_min_paragraph_length", DEFAULT_RAG_MIN_PARAGRAPH_LENGTH
    )

    if top_k <= 0:
        raise ValueError(f"top_k must be > 0, got {top_k}")
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be > 0, got {chunk_size}")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError(
            f"chunk_overlap must be in [0, chunk_size), "
            f"got overlap={chunk_overlap} size={chunk_size}"
        )
    if embed_batch_files <= 0:
        raise ValueError(f"embed_batch_files must be > 0, got {embed_batch_files}")
    if embed_batch_chars <= 0:
        raise ValueError(f"embed_batch_chars must be > 0, got {embed_batch_chars}")
    if not isinstance(summary_model, str) or not summary_model.strip():
        raise ValueError("summary_model must be a non-empty string")
    if rag_entropy_min < 0:
        raise ValueError(f"rag_entropy_min must be >= 0, got {rag_entropy_min}")
    if rag_entropy_max <= rag_entropy_min:
        raise ValueError(
            "rag_entropy_max must be greater than rag_entropy_min, "
            f"got min={rag_entropy_min} max={rag_entropy_max}"
        )
    if rag_min_paragraph_length <= 0:
        raise ValueError(f"rag_min_paragraph_length must be > 0, got {rag_min_paragraph_length}")

    return {
        "index_path": index_path,
        "top_k": top_k,
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "embed_batch_files": embed_batch_files,
        "embed_batch_chars": embed_batch_chars,
        "summary_model": summary_model,
        "rag_entropy_min": rag_entropy_min,
        "rag_entropy_max": rag_entropy_max,
        "rag_min_paragraph_length": rag_min_paragraph_length,
    }


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
        extensions = [
            validate_extension_rule(rule)
            for rule in entry.get("extensions", list(DEFAULT_EXTENSIONS))
        ]
        exclude = [validate_exclude_rule(rule) for rule in entry.get("exclude", [])]
        dirs.append(
            DirConfig(
                path=entry["path"],
                extensions=extensions,
                exclude=exclude,
                extractor_config=entry.get("extractor_config", {}),
            )
        )
    scalar_cfg = _load_scalar_config(data)

    return Config(
        dirs=dirs,
        index_path=scalar_cfg["index_path"],
        top_k=scalar_cfg["top_k"],
        embedding_model=data.get("embedding_model", DEFAULT_EMBEDDING_MODEL),
        summary_model=scalar_cfg["summary_model"],
        chunk_size=scalar_cfg["chunk_size"],
        chunk_overlap=scalar_cfg["chunk_overlap"],
        embed_batch_files=scalar_cfg["embed_batch_files"],
        embed_batch_chars=scalar_cfg["embed_batch_chars"],
        rag_entropy_min=scalar_cfg["rag_entropy_min"],
        rag_entropy_max=scalar_cfg["rag_entropy_max"],
        rag_min_paragraph_length=scalar_cfg["rag_min_paragraph_length"],
        openai_base_url=data.get("openai_base_url", ""),
        openai_api_key=data.get("openai_api_key", ""),
    )
