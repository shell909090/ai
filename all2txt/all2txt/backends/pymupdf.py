from pathlib import Path

from ..core.base import Extractor
from ..core.registry import registry


@registry.register("application/pdf")
class PyMuPDFExtractor(Extractor):
    """Extract text from PDF via PyMuPDF (fast, no JVM required)."""

    name = "pymupdf"
    priority = 15

    def available(self) -> bool:
        """Check that pymupdf is installed."""
        try:
            import pymupdf  # noqa: F401
        except ImportError:
            return False
        return True

    def extract(self, path: Path) -> str:
        """Open PDF with pymupdf, extract text page by page joined with double newlines."""
        import pymupdf

        doc = pymupdf.open(str(path))
        pages = [page.get_text() for page in doc]
        doc.close()
        return "\n\n".join(pages)
