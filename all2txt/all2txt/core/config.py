from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# MIME types for which file(1) output is too generic to be useful.
# When detect() gets one of these, it falls back to the extensions map.
_GENERIC_MIMES = frozenset(
    {
        "text/plain",
        "application/octet-stream",
        "application/xml",
        "text/xml",
        "application/json",
    }
)


@dataclass
class Config:
    """Loaded configuration from all2txt.yaml."""

    backends: dict[str, list[str]] = field(default_factory=dict)
    # mime → ordered list of backend names; listed backends go first,
    # remaining backends follow by their default priority.

    extractors: dict[str, dict[str, Any]] = field(default_factory=dict)
    # backend name → config dict passed to Extractor.__init__

    extensions: dict[str, str] = field(default_factory=dict)
    # lowercase file extension (with dot) → MIME override,
    # applied only when file(1) returns a generic MIME type.


def load_config(path: Path | None = None) -> Config:
    """Load config from path, defaulting to all2txt.yaml in cwd."""
    if path is None:
        path = Path("all2txt.yaml")
    if not path.exists():
        return Config()
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    backends = {mime: v.get("backends", []) for mime, v in data.get("mime", {}).items()}
    extractors: dict[str, dict[str, Any]] = data.get("extractor", {})
    extensions: dict[str, str] = data.get("extensions", {})
    return Config(backends=backends, extractors=extractors, extensions=extensions)
