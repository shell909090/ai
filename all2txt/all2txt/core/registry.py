import logging
import mimetypes
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
        """Return MIME type via file(1) or mimetypes fallback; apply extension override."""
        try:
            mime = subprocess.check_output(
                ["file", "--mime-type", "-b", str(path)], text=True
            ).strip()
        except FileNotFoundError:
            logger.warning("'file' command not found, falling back to mimetypes for MIME detection")
            guessed, _ = mimetypes.guess_type(str(path))
            mime = guessed or "application/octet-stream"
        if mime in _GENERIC_MIMES and self._config:
            override = self._config.extensions.get(path.suffix.lower())
            if override:
                logger.debug("extension override %s → %s", mime, override)
                mime = override
        logger.info("%s: mime type: %s", path.name, mime)
        return mime

    def extract(self, path: Path, mime: str | None = None) -> str:
        """Extract text from path, trying backends in priority order."""
        if mime is None:
            mime = self.detect(path)
        candidates = self._map.get(mime, [])
        errors: list[str] = []
        instances = []
        for cls in candidates:
            extractor_cfg: dict[str, Any] = dict(
                self._config.extractors.get(cls.name, {}) if self._config else {}
            )
            extractor_cfg["_mime"] = mime
            instances.append((cls, cls(config=extractor_cfg)))
        available_names = [cls.name for cls, inst in instances if inst.available()]
        all_names = [cls.name for cls, _ in instances]
        logger.info(
            "%s: %d registered backends: %s",
            path.name,
            len(candidates),
            ", ".join(all_names) or "none",
        )
        logger.info(
            "%s: %d available backends: %s",
            path.name,
            len(available_names),
            ", ".join(available_names) or "none",
        )
        if candidates and not available_names:
            hints = "\n".join(
                f"  {cls.name}: {cls.install_hint}" if cls.install_hint else f"  {cls.name}"
                for cls, _ in instances
            )
            logger.error(
                "%s: no backend available for %s. Install one of:\n%s",
                path.name,
                mime,
                hints,
            )
        for cls, inst in instances:
            if not inst.available():
                logger.debug("skipping %s (unavailable)", cls.__name__)
                continue
            try:
                logger.info("using %s for %s", cls.name, path.name)
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
