import logging

logger = logging.getLogger(__name__)

_BACKEND_MODULES = [
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

for _mod in _BACKEND_MODULES:
    try:
        __import__(f"{__name__}.{_mod}")
    except ImportError as _exc:
        logger.warning("backend module %r failed to load: %s", _mod, _exc)
