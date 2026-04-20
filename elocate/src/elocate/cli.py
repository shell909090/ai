"""CLI entry points: elocate (search) and elocate-updatedb (index builder)."""

import logging
import re
import sys
from pathlib import Path

import click

from elocate.config import DEFAULT_CONFIG_PATH, load_config
from elocate.indexer import Indexer
from elocate.searcher import Searcher

logger = logging.getLogger(__name__)

_CONFIG_OPTION = click.option(
    "--config",
    "config_path",
    default=None,
    type=click.Path(),
    help="Config file path (default: ~/.config/elocate/config.yaml).",
)

_NOISY_DEBUG_LOGGERS = ("openai", "httpx", "httpcore")


def _configure_logging(debug: bool) -> None:
    """Configure logging so debug mode stays focused on elocate output."""
    if not debug:
        return

    logging.basicConfig(level=logging.WARNING, force=True)
    logging.getLogger("elocate").setLevel(logging.DEBUG)
    for name in _NOISY_DEBUG_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


def _load_config_or_exit(config_path: str | None):  # type: ignore[return]
    """Load config from path or DEFAULT_CONFIG_PATH; print error and exit on failure."""
    cfg_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    try:
        return load_config(cfg_path)
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


def _print_results(results: list) -> None:
    for r in results:
        for path in r.paths:
            click.echo(f"{r.score:.4f}  {path}")
        if r.snippet:
            click.echo(f"         {r.snippet.replace(chr(10), ' ')[:200]}")


@click.command("elocate")
@click.argument("query")
@click.option("-k", "--top-k", default=None, type=int, help="Number of results to return.")
@click.option("-p", "--pattern", default=None, help="Regex pattern to filter results.")
@_CONFIG_OPTION
@click.option("--debug", is_flag=True, help="Enable debug logging.")
def main_search(
    query: str,
    top_k: int | None,
    pattern: str | None,
    config_path: str | None,
    debug: bool,
) -> None:
    """Search indexed documents by semantic query."""
    _configure_logging(debug)
    config = _load_config_or_exit(config_path)
    if top_k is not None:
        config.top_k = top_k

    if pattern:
        try:
            re.compile(pattern)
        except re.error as exc:
            click.echo(f"Error: invalid regex pattern: {exc}", err=True)
            sys.exit(1)

    try:
        searcher = Searcher(config)
        results = searcher.search(query, pattern=pattern)
    except (RuntimeError, ImportError, ValueError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    _print_results(results)

    if not results:
        click.echo("No results found.", err=True)
        sys.exit(1)


@click.command("elocate-updatedb")
@_CONFIG_OPTION
@click.option("--debug", is_flag=True, help="Enable debug logging.")
def main_updatedb(config_path: str | None, debug: bool) -> None:
    """Build or update the document vector index."""
    _configure_logging(debug)
    config = _load_config_or_exit(config_path)
    if not config.dirs:
        click.echo("Warning: no dirs configured. Nothing to index.", err=True)
        sys.exit(1)
    try:
        indexer = Indexer(config)
        added, updated, removed = indexer.run()
    except (ImportError, ValueError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    click.echo(f"Done: +{added} added, ~{updated} updated, -{removed} removed.")
