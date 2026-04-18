from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class Extractor(ABC):
    """Base class for all text extraction backends."""

    name: str = ""
    priority: int = 50
    install_hint: str = ""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg: dict[str, Any] = config or {}

    @abstractmethod
    def extract(self, path: Path) -> str:
        """Extract plain text from path, raise on failure."""
        ...

    def available(self) -> bool:
        """Return True if the backend's external dependencies are present."""
        return True
