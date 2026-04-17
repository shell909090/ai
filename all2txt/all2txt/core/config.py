import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    """Loaded configuration from all2txt.toml."""

    backends: dict[str, list[str]] = field(default_factory=dict)


def load_config(path: Path | None = None) -> Config:
    """Load config from path, defaulting to all2txt.toml in cwd."""
    if path is None:
        path = Path("all2txt.toml")
    if not path.exists():
        return Config()
    with open(path, "rb") as f:
        data = tomllib.load(f)
    mime_section = data.get("mime", {})
    backends = {mime: v.get("backends", []) for mime, v in mime_section.items()}
    return Config(backends=backends)
