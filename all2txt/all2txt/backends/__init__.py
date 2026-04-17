# Import all backends to trigger self-registration with the registry.
from . import (
    asr,
    libreoffice,
    native_office,
    ocr,
    openai_vision,
    pandoc,
    plaintext,
    pymupdf,
    system,
    tika,
    unstructured,
)

__all__ = [
    "asr",
    "libreoffice",
    "native_office",
    "ocr",
    "openai_vision",
    "pandoc",
    "plaintext",
    "pymupdf",
    "system",
    "tika",
    "unstructured",
]
