from pathlib import Path

from ..core.base import Extractor
from ..core.registry import registry


@registry.register(
    "text/plain", "text/csv", "text/markdown", "text/x-python", "text/x-script.python"
)
class PlainTextExtractor(Extractor):
    """Read plain text files directly."""

    name = "plaintext"
    priority = 1

    def extract(self, path: Path) -> str:
        """Read file content as UTF-8, replacing undecodable bytes."""
        return path.read_text(errors="replace")
