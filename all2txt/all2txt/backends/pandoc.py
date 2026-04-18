import shutil
import subprocess
from pathlib import Path

from ..core.base import Extractor
from ..core.registry import registry

# Maps registered MIME types to the pandoc -f reader name.
_MIME_TO_READER: dict[str, str] = {
    "text/x-tex": "latex",
    "text/troff": "man",
    "text/html": "html",
    "application/xhtml+xml": "html",
    "application/epub+zip": "epub",
    "application/vnd.oasis.opendocument.text": "odt",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "text/x-rst": "rst",
    "text/x-org": "org",
    "text/rtf": "rtf",
    "application/rtf": "rtf",
    "text/x-opml": "opml",
    "application/docbook+xml": "docbook",
    "application/x-fictionbook+xml": "fb2",
    "application/x-ipynb+json": "ipynb",
    "text/x-creole": "creole",
    "text/x-textile": "textile",
}


@registry.register(*_MIME_TO_READER.keys())
class PandocExtractor(Extractor):
    """Convert documents to plain text via pandoc CLI."""

    name = "pandoc"
    priority = 10
    install_hint = "apt install pandoc"

    def available(self) -> bool:
        """Check that pandoc is installed."""
        return shutil.which("pandoc") is not None

    def extract(self, path: Path) -> str:
        """Run pandoc -f <reader> -t plain --wrap=none and return stdout."""
        mime = self._cfg.get("_mime", "")
        reader = _MIME_TO_READER.get(mime)
        cmd = ["pandoc", "-t", "plain", "--wrap=none"]
        if reader:
            cmd += ["-f", reader]
        cmd.append(str(path))
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout
