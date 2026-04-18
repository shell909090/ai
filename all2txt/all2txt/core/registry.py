import logging
import subprocess
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from .base import Extractor
from .config import _GENERIC_MIMES, Config

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=type[Extractor])


class Registry:
    """Maps MIME types to prioritised chains of Extractor backends."""

    def __init__(self) -> None:
        self._map: dict[str, list[type[Extractor]]] = defaultdict(list)
        self._config: Config | None = None

    def register(self, *mimes: str) -> Callable[[T], T]:
        """Decorator: register an Extractor class for one or more MIME types."""

        def decorator(cls: T) -> T:
            for mime in mimes:
                self._map[mime].append(cls)
                self._sort(mime)
            logger.debug("registered %s for %s", cls.__name__, mimes)
            return cls

        return decorator

    def configure(self, config: Config) -> None:
        """Apply config overrides and re-sort all MIME chains."""
        self._config = config
        for mime in self._map:
            self._sort(mime)

    def detect(self, path: Path) -> str:
        """Return MIME type via file(1); apply extension override for generic results."""
        mime = subprocess.check_output(["file", "--mime-type", "-b", str(path)], text=True).strip()
        if mime in _GENERIC_MIMES and self._config:
            override = self._config.extensions.get(path.suffix.lower())
            if override:
                logger.debug("extension override %s → %s", mime, override)
                mime = override
        logger.debug("detected %s → %s", path, mime)
        return mime

    def extract(self, path: Path, mime: str | None = None) -> str:
        """Extract text from path, trying backends in priority order."""
        if mime is None:
            mime = self.detect(path)
        candidates = self._map.get(mime, [])
        errors: list[str] = []
        for cls in candidates:
            extractor_cfg: dict[str, Any] = (
                self._config.extractors.get(cls.name, {}) if self._config else {}
            )
            inst = cls(config=extractor_cfg)
            if not inst.available():
                logger.debug("skipping %s (unavailable)", cls.__name__)
                continue
            try:
                logger.debug("trying %s for %s", cls.__name__, path)
                return inst.extract(path)
            except Exception as exc:
                logger.debug("%s failed: %s", cls.__name__, exc)
                errors.append(f"{cls.__name__}: {exc}")
        raise RuntimeError(f"No backend succeeded for {mime} ({path}). Errors: {errors}")

    def _sort(self, mime: str) -> None:
        order = self._config.backends.get(mime, []) if self._config else []

        def key(cls: type[Extractor]) -> tuple[int, int]:
            name = getattr(cls, "name", "")
            if order and name in order:
                return (0, order.index(name))
            return (1, cls.priority)

        self._map[mime].sort(key=key)


registry = Registry()
