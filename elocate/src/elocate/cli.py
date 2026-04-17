"""CLI entry points: elocate (search) and elocate-updatedb (index builder)."""

import logging
import sys

import click

from elocate.config import load_config
from elocate.indexer import Indexer
from elocate.searcher import Searcher

logger = logging.getLogger(__name__)


@click.command("elocate")
@click.argument("query")
@click.option("-k", "--top-k", default=None, type=int, help="Number of results to return.")
@click.option("-p", "--pattern", default=None, help="Regex pattern to filter results.")
@click.option("--debug", is_flag=True, help="Enable debug logging.")
def main_search(query: str, top_k: int | None, pattern: str | None, debug: bool) -> None:
    """Search indexed documents by semantic query."""
    if debug:
        logging.basicConfig(level=logging.DEBUG)
    config = load_config()
    if top_k is not None:
        config.top_k = top_k
    searcher = Searcher(config)
    results = searcher.search(query, pattern=pattern)
    for r in results:
        click.echo(f"{r.score:.4f}  {r.path}")
    if not results:
        click.echo("No results found.", err=True)
        sys.exit(1)


@click.command("elocate-updatedb")
@click.option("--debug", is_flag=True, help="Enable debug logging.")
def main_updatedb(debug: bool) -> None:
    """Build or update the document vector index."""
    if debug:
        logging.basicConfig(level=logging.DEBUG)
    config = load_config()
    if not config.index_dirs:
        click.echo("Warning: no index_dirs configured. Nothing to index.", err=True)
        sys.exit(1)
    indexer = Indexer(config)
    count = indexer.run()
    click.echo(f"Indexed {count} documents.")
