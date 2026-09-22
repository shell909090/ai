"""Check Python functions using the cognitive-complexity package."""

import argparse
import ast
import logging
from collections.abc import Iterator
from pathlib import Path
import tokenize

from cognitive_complexity.api import get_cognitive_complexity

MAX_COMPLEXITY = 15
EXCLUDED_DIRS = {
    ".git", ".venv", "venv", "env", "ENV", "__pycache__", ".cache",
    ".ruff_cache", ".pytest_cache", ".mypy_cache", ".tox", ".nox",
}
logger = logging.getLogger(__name__)


def python_files(root: Path) -> Iterator[Path]:
    """Find project Python files while excluding environments and caches."""
    for directory, dirs, files in root.walk():
        dirs[:] = sorted(name for name in dirs if name not in EXCLUDED_DIRS)
        for name in sorted(files):
            path = directory / name
            if path.suffix == ".py" and not path.is_symlink():
                yield path


def function_scores(path: Path) -> list[tuple[int, str, int]]:
    """Score all named functions, including methods, nested and async functions."""
    with tokenize.open(path) as source:
        tree = ast.parse(source.read(), filename=str(path))
    return [
        (node.lineno, node.name, get_cognitive_complexity(node))
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def check_project(root: Path) -> int:
    """Return nonzero when scanning fails or cognitive complexity exceeds 15."""
    file_count = function_count = violations = highest = 0
    for path in python_files(root):
        file_count += 1
        try:
            scores = function_scores(path)
        except (OSError, SyntaxError, UnicodeError) as exc:
            logger.error("Cannot scan %s: %s", path, exc)
            violations += 1
            continue
        function_count += len(scores)
        for line, name, score in scores:
            highest = max(highest, score)
            if score > MAX_COMPLEXITY:
                logger.error("%s:%d: %s cognitive complexity %d > %d", path, line, name, score, MAX_COMPLEXITY)
                violations += 1
    if file_count == 0:
        logger.error("No Python files found in %s", root)
        return 1
    logger.info("Scanned %d files, %d functions; maximum=%d, violations=%d",
                file_count, function_count, highest, violations)
    return int(violations > 0)


def main() -> int:
    """Run cognitive complexity checks for the specified project directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, nargs="?", default=Path("."))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if not args.root.is_dir():
        logger.error("Not a project directory: %s", args.root)
        return 1
    return check_project(args.root)


if __name__ == "__main__":
    raise SystemExit(main())
