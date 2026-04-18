import argparse
import logging
import sys
from pathlib import Path

from . import backends as _backends_module  # noqa: F401 — triggers registration
from .core.config import load_config
from .core.registry import registry


def main() -> None:
    """CLI entry point: extract plain text from one or more files."""
    parser = argparse.ArgumentParser(
        prog="all2txt",
        description="Extract plain text from any file format.",
    )
    parser.add_argument("files", nargs="+", type=Path, metavar="FILE")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        metavar="FILE",
        help="Path to all2txt.yaml (default: ./all2txt.yaml)",
    )
    parser.add_argument("--mime", metavar="MIME", help="Override MIME type detection")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable info logging")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    level = logging.WARNING
    if args.debug:
        level = logging.DEBUG
    elif args.verbose:
        level = logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")

    config = load_config(args.config)
    registry.configure(config)

    exit_code = 0
    for path in args.files:
        try:
            text = registry.extract(path, mime=args.mime)
            sys.stdout.write(text)
            if not text.endswith("\n"):
                sys.stdout.write("\n")
        except Exception as exc:
            print(f"error: {path}: {exc}", file=sys.stderr)
            exit_code = 1

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
