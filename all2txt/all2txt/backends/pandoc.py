import importlib
import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..core.base import Extractor
from ..core.registry import registry

logger = logging.getLogger(__name__)

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

_HTML_MIMES = {"text/html", "application/xhtml+xml"}
_HEADER_SCAN_LIMIT = 8192
_HEADER_CHARSET_RE = re.compile(
    rb"<meta\b[^>]*\bcharset\s*=\s*['\"]?\s*([A-Za-z0-9._:-]+)",
    re.IGNORECASE,
)
_HEADER_CONTENT_TYPE_RE = re.compile(
    rb"<meta\b[^>]*\bhttp-equiv\s*=\s*['\"]?content-type['\"]?[^>]*\bcontent\s*=\s*"
    rb"['\"][^'\"]*\bcharset\s*=\s*([A-Za-z0-9._:-]+)",
    re.IGNORECASE,
)
_BOM_ENCODINGS: tuple[tuple[bytes, str], ...] = (
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xff\xfe\x00\x00", "utf-32"),
    (b"\x00\x00\xfe\xff", "utf-32"),
    (b"\xff\xfe", "utf-16"),
    (b"\xfe\xff", "utf-16"),
)
_ENCODING_ALIASES = {
    "gb2312": "gb18030",
    "gbk": "gb18030",
    "gb_2312-80": "gb18030",
}


def _normalize_encoding(encoding: str) -> str:
    """Map encoding aliases to Python codec names."""
    normalized = encoding.strip().strip("\"'").lower()
    return _ENCODING_ALIASES.get(normalized, normalized)


def _detect_bom_encoding(raw: bytes) -> str | None:
    """Return the encoding declared by a Unicode BOM."""
    for bom, encoding in _BOM_ENCODINGS:
        if raw.startswith(bom):
            return encoding
    return None


def _detect_header_encoding(raw: bytes) -> str | None:
    """Return the charset declared in the HTML header."""
    head = raw[:_HEADER_SCAN_LIMIT]
    for pattern in (_HEADER_CHARSET_RE, _HEADER_CONTENT_TYPE_RE):
        match = pattern.search(head)
        if match:
            return _normalize_encoding(match.group(1).decode("ascii", errors="ignore"))
    return None


def _detect_with_chardet(raw: bytes) -> str:
    """Return a charset guess from chardet."""
    try:
        chardet = importlib.import_module("chardet")
    except ImportError as exc:
        raise RuntimeError(
            "HTML encoding fallback requires chardet; install it with `uv pip install chardet`"
        ) from exc
    result: Any = chardet.detect(raw)
    encoding = result.get("encoding") if isinstance(result, dict) else None
    if not encoding:
        raise RuntimeError("chardet could not determine the HTML encoding")
    return _normalize_encoding(encoding)


def _decode_html(raw: bytes, path: Path) -> str:
    """Decode HTML bytes using header metadata before chardet fallback."""
    bom_encoding = _detect_bom_encoding(raw)
    if bom_encoding:
        logger.debug("%s: decoded HTML using BOM encoding %s", path.name, bom_encoding)
        return raw.decode(bom_encoding)

    header_encoding = _detect_header_encoding(raw)
    if header_encoding:
        try:
            text = raw.decode(header_encoding)
            logger.debug("%s: decoded HTML using header encoding %s", path.name, header_encoding)
            return text
        except (LookupError, UnicodeDecodeError) as exc:
            logger.warning(
                "%s: failed to decode HTML with header encoding %s: %s; falling back to chardet",
                path.name,
                header_encoding,
                exc,
            )

    guessed_encoding = _detect_with_chardet(raw)
    logger.debug("%s: decoded HTML using chardet encoding %s", path.name, guessed_encoding)
    return raw.decode(guessed_encoding)


@registry.register(*_MIME_TO_READER.keys())
class PandocExtractor(Extractor):
    """Convert documents to plain text via pandoc CLI."""

    name = "pandoc"
    priority = 10
    install_hint = "apt install pandoc && uv pip install chardet"

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
        if mime in _HTML_MIMES:
            html = _decode_html(path.read_bytes(), path)
            cmd.append("-")
            result = subprocess.run(
                cmd,
                input=html,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
        else:
            cmd.append(str(path))
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout
