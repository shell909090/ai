import shutil
from pathlib import Path

from ..core.base import Extractor
from ..core.registry import registry


@registry.register("text/troff")
class ManExtractor(Extractor):
    """Render man/troff pages to plain text via groff + col."""

    name = "man"
    priority = 5

    def available(self) -> bool:
        """Check that groff and col are installed."""
        return shutil.which("groff") is not None and shutil.which("col") is not None

    def extract(self, path: Path) -> str:
        """Run groff -Tascii -man then col -bx to strip formatting."""
        raise NotImplementedError


@registry.register("text/x-info")
class InfoExtractor(Extractor):
    """Extract text from GNU Info files via the info CLI."""

    name = "info"
    priority = 5

    def available(self) -> bool:
        """Check that the info command is installed."""
        return shutil.which("info") is not None

    def extract(self, path: Path) -> str:
        """Run info --subnodes --output=- --file=<path>."""
        raise NotImplementedError
