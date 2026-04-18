import shutil
import subprocess
from pathlib import Path

from ..core.base import Extractor
from ..core.registry import registry


@registry.register("application/pdf")
class PdfToTextExtractor(Extractor):
    """Extract text from PDF via pdftotext (Poppler)."""

    name = "pdftotext"
    priority = 20
    install_hint = "apt install poppler-utils"

    def available(self) -> bool:
        """Check that pdftotext is installed."""
        return shutil.which("pdftotext") is not None

    def extract(self, path: Path) -> str:
        """Run pdftotext -layout and return stdout."""
        result = subprocess.run(
            ["pdftotext", "-layout", str(path), "-"],
            capture_output=True,
            check=True,
        )
        return result.stdout.decode(errors="replace")


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
        import subprocess

        groff = subprocess.run(
            ["groff", "-Tascii", "-man", str(path)],
            capture_output=True,
            check=True,
        )
        col = subprocess.run(
            ["col", "-bx"],
            input=groff.stdout,
            capture_output=True,
            check=True,
        )
        return col.stdout.decode(errors="replace")


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
        import subprocess

        result = subprocess.run(
            ["info", "--subnodes", "--output=-", f"--file={path}"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
