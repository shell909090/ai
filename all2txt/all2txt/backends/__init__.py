# Import all backends to trigger self-registration with the registry.
from . import pandoc, plaintext, pymupdf, system, tika, unstructured

__all__ = ["pandoc", "plaintext", "pymupdf", "system", "tika", "unstructured"]
