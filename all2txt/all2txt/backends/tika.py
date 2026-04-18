from pathlib import Path

from ..core.base import Extractor
from ..core.registry import registry

_TIKA_MIMES = (
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.oasis.opendocument.text",
    "application/vnd.oasis.opendocument.spreadsheet",
    "application/vnd.oasis.opendocument.presentation",
    "text/rtf",
    "application/rtf",
)


@registry.register(*_TIKA_MIMES)
class TikaExtractor(Extractor):
    """Extract text via Apache Tika (requires tika Python package + JVM)."""

    name = "tika"
    priority = 20

    def available(self) -> bool:
        """Check that the tika Python package is installed."""
        try:
            import tika  # noqa: F401
        except ImportError:
            return False
        return True

    def extract(self, path: Path) -> str:
        """Call tika.parser.from_file and return stripped content field."""
        from tika import parser as tika_parser

        parsed = tika_parser.from_file(str(path))
        content = parsed.get("content") or ""
        return content.strip()
