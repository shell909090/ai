"""Unit tests for all2txt.core.registry.Registry."""

from pathlib import Path
from unittest.mock import patch

import pytest

from all2txt.core.base import Extractor
from all2txt.core.config import Config
from all2txt.core.registry import Registry

# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def make_extractor(
    name: str,
    priority: int = 50,
    *,
    available: bool = True,
    extract_result: str | Exception = "extracted text",
) -> type[Extractor]:
    """Return a fresh Extractor subclass with controllable behaviour."""

    def _extract(self: Extractor, path: Path) -> str:
        if isinstance(extract_result, Exception):
            raise extract_result
        return extract_result

    def _available(self: Extractor) -> bool:
        return available

    cls = type(
        f"Extractor_{name}",
        (Extractor,),
        {
            "name": name,
            "priority": priority,
            "extract": _extract,
            "available": _available,
        },
    )
    return cls  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# 1. Register a backend and verify it appears in _map
# ---------------------------------------------------------------------------


def test_register_appears_in_map() -> None:
    reg = Registry()
    cls = make_extractor("alpha")

    reg.register("application/pdf")(cls)

    assert "application/pdf" in reg._map
    assert cls in reg._map["application/pdf"]


# ---------------------------------------------------------------------------
# 2. Priority sorting: lower priority number goes first
# ---------------------------------------------------------------------------


def test_priority_sorting() -> None:
    reg = Registry()
    low_prio = make_extractor("low", priority=10)
    high_prio = make_extractor("high", priority=90)

    # Register higher-priority number first to ensure sort actually runs.
    reg.register("text/html")(high_prio)
    reg.register("text/html")(low_prio)

    chain = reg._map["text/html"]
    assert chain[0] is low_prio
    assert chain[1] is high_prio


# ---------------------------------------------------------------------------
# 3. Config override: configure() reorders via backends list
# ---------------------------------------------------------------------------


def test_configure_reorders_backends() -> None:
    reg = Registry()
    alpha = make_extractor("alpha", priority=10)
    beta = make_extractor("beta", priority=20)
    gamma = make_extractor("gamma", priority=30)

    for cls in (alpha, beta, gamma):
        reg.register("image/png")(cls)

    # Without config: alpha < beta < gamma by priority.
    assert reg._map["image/png"][0] is alpha

    # Config puts gamma first, then beta; alpha is unlisted → falls back to priority.
    cfg = Config(backends={"image/png": ["gamma", "beta"]})
    reg.configure(cfg)

    chain = reg._map["image/png"]
    assert chain[0] is gamma
    assert chain[1] is beta
    assert chain[2] is alpha


# ---------------------------------------------------------------------------
# 4. Fallback: first backend raises, second returns text
# ---------------------------------------------------------------------------


def test_fallback_to_second_backend(tmp_path: Path) -> None:
    reg = Registry()
    failing = make_extractor("failing", priority=10, extract_result=RuntimeError("boom"))
    working = make_extractor("working", priority=20, extract_result="hello world")

    reg.register("text/html")(failing)
    reg.register("text/html")(working)

    dummy = tmp_path / "page.html"
    dummy.write_text("<p>hi</p>")

    result = reg.extract(dummy, mime="text/html")
    assert result == "hello world"


# ---------------------------------------------------------------------------
# 5. Extension override: detect() upgrades generic MIME via Config.extensions
# ---------------------------------------------------------------------------


def test_detect_extension_override(tmp_path: Path) -> None:
    reg = Registry()
    rst_file = tmp_path / "doc.rst"
    rst_file.write_text(".. title::\n")

    cfg = Config(extensions={".rst": "text/x-rst"})
    reg.configure(cfg)

    with patch("subprocess.check_output", return_value="text/plain") as mock_sub:
        mime = reg.detect(rst_file)

    mock_sub.assert_called_once_with(["file", "--mime-type", "-b", str(rst_file)], text=True)
    assert mime == "text/x-rst"


def test_detect_no_override_for_specific_mime(tmp_path: Path) -> None:
    """When file(1) returns a non-generic MIME, extensions map is not applied."""
    reg = Registry()
    pdf_file = tmp_path / "doc.pdf"
    pdf_file.write_bytes(b"%PDF-1.4")

    cfg = Config(extensions={".pdf": "application/x-custom"})
    reg.configure(cfg)

    with patch("subprocess.check_output", return_value="application/pdf"):
        mime = reg.detect(pdf_file)

    assert mime == "application/pdf"


# ---------------------------------------------------------------------------
# 6. available() returning False skips backend
# ---------------------------------------------------------------------------


def test_unavailable_backend_is_skipped(tmp_path: Path) -> None:
    reg = Registry()
    unavailable = make_extractor("unavailable", priority=10, available=False, extract_result="NOPE")
    fallback = make_extractor("fallback", priority=20, extract_result="ok")

    reg.register("application/pdf")(unavailable)
    reg.register("application/pdf")(fallback)

    dummy = tmp_path / "file.pdf"
    dummy.write_bytes(b"%PDF")

    result = reg.extract(dummy, mime="application/pdf")
    assert result == "ok"


# ---------------------------------------------------------------------------
# 7. extract() raises RuntimeError when all backends fail
# ---------------------------------------------------------------------------


def test_extract_raises_when_all_backends_fail(tmp_path: Path) -> None:
    reg = Registry()
    bad1 = make_extractor("bad1", priority=10, extract_result=ValueError("err1"))
    bad2 = make_extractor("bad2", priority=20, extract_result=OSError("err2"))

    reg.register("application/zip")(bad1)
    reg.register("application/zip")(bad2)

    dummy = tmp_path / "archive.zip"
    dummy.write_bytes(b"PK")

    with pytest.raises(RuntimeError) as exc_info:
        reg.extract(dummy, mime="application/zip")

    assert "bad1" in str(exc_info.value)
    assert "bad2" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 8. No backends registered for MIME → RuntimeError
# ---------------------------------------------------------------------------


def test_extract_raises_for_unregistered_mime(tmp_path: Path) -> None:
    reg = Registry()
    dummy = tmp_path / "mystery.bin"
    dummy.write_bytes(b"\x00\x01\x02")

    with pytest.raises(RuntimeError):
        reg.extract(dummy, mime="application/x-unknown")


# ---------------------------------------------------------------------------
# 9. _mime is injected into extractor config
# ---------------------------------------------------------------------------


def test_extract_injects_mime_into_extractor_config(tmp_path: Path) -> None:
    """Registry must pass _mime in the config dict so backends can use it."""
    received: dict[str, object] = {}

    class CapturingExtractor(Extractor):
        name = "capturing"
        priority = 1

        def __init__(self, config: dict | None = None) -> None:
            super().__init__(config)
            received.update(self._cfg)

        def extract(self, path: Path) -> str:
            return "ok"

    reg = Registry()
    reg.register("text/plain")(CapturingExtractor)

    dummy = tmp_path / "file.txt"
    dummy.write_text("hi")
    reg.extract(dummy, mime="text/plain")

    assert received.get("_mime") == "text/plain"


# ---------------------------------------------------------------------------
# 10. Three-tier MIME detection
# ---------------------------------------------------------------------------


def test_detect_octet_stream_falls_back_to_mimetypes(tmp_path: Path) -> None:
    """file returns octet-stream for .info → mimetypes provides application/x-info."""
    reg = Registry()
    info_file = tmp_path / "manual.info"
    info_file.write_text("INFO content")

    with (
        patch("subprocess.check_output", return_value="application/octet-stream"),
        patch(
            "all2txt.core.registry.mimetypes.guess_type", return_value=("application/x-info", None)
        ),
    ):
        mime = reg.detect(info_file)

    assert mime == "application/x-info"


def test_detect_octet_stream_falls_back_to_ext_map(tmp_path: Path) -> None:
    """file returns octet-stream for .1 and mimetypes returns None → _EXT_MAP gives text/troff."""
    reg = Registry()
    man_file = tmp_path / "ls.1"
    man_file.write_text(".TH LS 1")

    with (
        patch("subprocess.check_output", return_value="application/octet-stream"),
        patch("all2txt.core.registry.mimetypes.guess_type", return_value=(None, None)),
    ):
        mime = reg.detect(man_file)

    assert mime == "text/troff"


def test_detect_file_not_found_falls_back_to_mimetypes(tmp_path: Path) -> None:
    """file command missing → mimetypes provides application/x-info."""
    reg = Registry()
    info_file = tmp_path / "manual.info"
    info_file.write_text("INFO content")

    with (
        patch("subprocess.check_output", side_effect=FileNotFoundError),
        patch(
            "all2txt.core.registry.mimetypes.guess_type", return_value=("application/x-info", None)
        ),
    ):
        mime = reg.detect(info_file)

    assert mime == "application/x-info"


def test_detect_file_not_found_and_mimetypes_none_uses_ext_map(tmp_path: Path) -> None:
    """file command missing and mimetypes returns None for .1 → _EXT_MAP gives text/troff."""
    reg = Registry()
    man_file = tmp_path / "ls.1"
    man_file.write_text(".TH LS 1")

    with (
        patch("subprocess.check_output", side_effect=FileNotFoundError),
        patch("all2txt.core.registry.mimetypes.guess_type", return_value=(None, None)),
    ):
        mime = reg.detect(man_file)

    assert mime == "text/troff"
