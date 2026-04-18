from pathlib import Path
from typing import Any

from ..core.base import Extractor
from ..core.registry import registry

_IMAGE_MIMES = (
    "image/png",
    "image/jpeg",
    "image/tiff",
    "image/bmp",
    "image/webp",
    "image/gif",
)


@registry.register(*_IMAGE_MIMES)
class TesseractExtractor(Extractor):
    """Traditional OCR via Tesseract (pytesseract + tesseract CLI).

    Config keys:
      lang (str): Tesseract language string, e.g. "eng+chi_sim". Default: "eng".
      psm  (int): Page segmentation mode (0-13). Default: 3.
    """

    name = "tesseract"
    priority = 40

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._lang: str = self._cfg.get("lang", "eng")
        self._psm: int = int(self._cfg.get("psm", 3))

    def available(self) -> bool:
        """Check that pytesseract and tesseract CLI are installed."""
        try:
            import pytesseract  # noqa: F401
        except ImportError:
            return False
        return True

    def extract(self, path: Path) -> str:
        """Run pytesseract.image_to_string with configured lang and psm."""
        import pytesseract
        from PIL import Image

        img = Image.open(str(path))
        config = f"--psm {self._psm}"
        return pytesseract.image_to_string(img, lang=self._lang, config=config)


@registry.register(*_IMAGE_MIMES)
class EasyOCRExtractor(Extractor):
    """ML-based OCR via EasyOCR (multi-language, GPU-optional).

    Config keys:
      langs (list[str]): Language codes, e.g. ["en", "ch_sim"]. Default: ["en"].
    """

    name = "easyocr"
    priority = 45

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._langs: list[str] = self._cfg.get("langs", ["en"])

    def available(self) -> bool:
        """Check that easyocr is installed."""
        try:
            import easyocr  # noqa: F401
        except ImportError:
            return False
        return True

    def extract(self, path: Path) -> str:
        """Run easyocr.Reader.readtext and join detected strings."""
        import easyocr

        reader = easyocr.Reader(self._langs)
        results = reader.readtext(str(path), detail=0)
        return "\n".join(results)


@registry.register(*_IMAGE_MIMES)
class PaddleOCRExtractor(Extractor):
    """OCR via PaddleOCR (strong CJK support).

    Config keys:
      lang (str): Language code, e.g. "ch", "en". Default: "ch".
    """

    name = "paddleocr"
    priority = 46

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._lang: str = self._cfg.get("lang", "ch")

    def available(self) -> bool:
        """Check that paddleocr is installed."""
        try:
            from paddleocr import PaddleOCR  # noqa: F401
        except ImportError:
            return False
        return True

    def extract(self, path: Path) -> str:
        """Run PaddleOCR().ocr and join detected text lines."""
        from paddleocr import PaddleOCR

        ocr = PaddleOCR(use_angle_cls=True, lang=self._lang)
        result = ocr.ocr(str(path), cls=True)
        lines: list[str] = []
        for page in result:
            if page:
                for line in page:
                    text = line[1][0]
                    lines.append(text)
        return "\n".join(lines)
