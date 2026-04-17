import shutil
from pathlib import Path

from ..core.base import Extractor
from ..core.registry import registry

_OFFICE_MIMES = (
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


@registry.register(*_OFFICE_MIMES)
class LibreOfficeExtractor(Extractor):
    """Convert Office/ODF documents to plain text via LibreOffice headless."""

    name = "libreoffice"
    priority = 25

    def available(self) -> bool:
        """Check that libreoffice (or soffice) is installed."""
        return shutil.which("libreoffice") is not None or shutil.which("soffice") is not None

    def extract(self, path: Path) -> str:
        """Run libreoffice --headless --convert-to txt, read result, then clean up."""
        raise NotImplementedError
