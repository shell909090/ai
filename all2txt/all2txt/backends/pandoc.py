import shutil
from pathlib import Path

from ..core.base import Extractor
from ..core.registry import registry


@registry.register(
    "text/x-tex",
    "text/troff",
    "text/html",
    "application/xhtml+xml",
    "application/epub+zip",
    "application/vnd.oasis.opendocument.text",
)
class PandocExtractor(Extractor):
    """Convert documents to plain text via pandoc CLI."""

    name = "pandoc"
    priority = 10

    def available(self) -> bool:
        """Check that pandoc is installed."""
        return shutil.which("pandoc") is not None

    def extract(self, path: Path) -> str:
        """Run pandoc -t plain --wrap=none and return stdout."""
        raise NotImplementedError
