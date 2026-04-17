from pathlib import Path

from ..core.base import Extractor
from ..core.registry import registry


@registry.register("application/vnd.openxmlformats-officedocument.wordprocessingml.document")
class NativeDocxExtractor(Extractor):
    """Extract text from .docx via python-docx (paragraphs and tables)."""

    name = "python_docx"
    priority = 18

    def available(self) -> bool:
        """Check that python-docx is installed."""
        try:
            import docx  # noqa: F401
        except ImportError:
            return False
        return True

    def extract(self, path: Path) -> str:
        """Yield all paragraph and table-cell text joined by newlines."""
        raise NotImplementedError


@registry.register("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
class NativeXlsxExtractor(Extractor):
    """Extract text from .xlsx via openpyxl (all sheets, row by row)."""

    name = "openpyxl"
    priority = 18

    def available(self) -> bool:
        """Check that openpyxl is installed."""
        try:
            import openpyxl  # noqa: F401
        except ImportError:
            return False
        return True

    def extract(self, path: Path) -> str:
        """Tab-separate cells, newline-separate rows, blank-line-separate sheets."""
        raise NotImplementedError


@registry.register(
    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
)
class NativePptxExtractor(Extractor):
    """Extract text from .pptx via python-pptx (all slides, all text frames)."""

    name = "python_pptx"
    priority = 18

    def available(self) -> bool:
        """Check that python-pptx is installed."""
        try:
            import pptx  # noqa: F401
        except ImportError:
            return False
        return True

    def extract(self, path: Path) -> str:
        """Collect text from every shape on every slide, joined by newlines."""
        raise NotImplementedError
