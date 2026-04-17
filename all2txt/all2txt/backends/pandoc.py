import shutil
from pathlib import Path

from ..core.base import Extractor
from ..core.registry import registry


@registry.register(
    # LaTeX
    "text/x-tex",
    # Man / troff
    "text/troff",
    # HTML
    "text/html",
    "application/xhtml+xml",
    # E-book
    "application/epub+zip",
    # Word / ODT
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.oasis.opendocument.text",
    # RTF
    "text/rtf",
    "application/rtf",
    # Markup / wiki
    "text/x-rst",
    "text/x-org",
    "text/x-opml",
    "text/x-creole",
    "text/x-textile",
    # Structured documents
    "application/docbook+xml",
    "application/x-fictionbook+xml",
    # Jupyter notebook (.ipynb maps here via extensions override)
    "application/x-ipynb+json",
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
