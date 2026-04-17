from pathlib import Path

from ..core.base import Extractor
from ..core.registry import registry


@registry.register(
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/tiff",
    "image/bmp",
    "image/webp",
)
class UnstructuredExtractor(Extractor):
    """Extract text via unstructured (supports OCR for images and scanned PDFs)."""

    name = "unstructured"
    priority = 30

    def available(self) -> bool:
        """Check that unstructured is installed."""
        try:
            from unstructured.partition.auto import partition  # noqa: F401
        except ImportError:
            return False
        return True

    def extract(self, path: Path) -> str:
        """Partition file with unstructured and join all text elements."""
        raise NotImplementedError
