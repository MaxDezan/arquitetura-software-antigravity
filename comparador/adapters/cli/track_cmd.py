import asyncio
import csv
import logging
from pathlib import Path

import click

from comparador.adapters.sources.crawler.crawler_source import SITES, CrawlerSource
from comparador.adapters.sources.crawler.fetcher import RateLimitedFetcher
from comparador.adapters.storage.sqlite.repository import SqliteProductRepository
from comparador.application.track_prices import TrackPricesUseCase
from comparador.domain.models import ProductQuery

log = logging.getLogger(__name__)


def _load_products(path: Path) -> list[ProductQuery]:
    products: list[ProductQuery] = []
    with path.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("name") or row.get("nome") or "").strip()
            if not name:
                continue
            products.append(
                ProductQuery(
                    name=name,
                    reference_model=(
                        row.get("reference_model") or row.get("modelo") or None
                    ) or None,
                    notes=(row.get("notes") or None) or None,
                )
            )
    return products


@click.command("track")
@click.option("-i", "--input", "input_path",
              default="products.csv",
              type=click.Path(exists=True, path_type=Path),
              help="CSV with columns: name, reference_model (opt), notes (opt)")
@click.option("--db", "db_path",
              default="data/comparador.db",
              type=click.Path(path_type=Path),
              help="SQLite database path")
@click.option("--top", default=5, show_default=True,
              help="Top N results per site per product")
@click.option("--sites", default="mercadolivre,amazon,magalu",
              show_default=True, help="Comma-separated site list")
@click.option("--headful", is_flag=True, help="Run browser visibly (debug)")
@click.option("--min-delay", default=3.0, show_default=True)
@click.option("--max-delay", default=8.0, show_default=True)
def track(input_path, db_path, top, sites, headful, min_delay, max_delay):
    """Crawl configured sites and append price snapshots to the DB."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    wanted = [s.strip() for s in sites.split(",") if s.strip()]
    unknown = set(wanted) - SITES.keys()
    if unknown:
        raise click.BadParameter(f"unknown sites: {', '.join(unknown)}")

    asyncio.run(_run(input_path, db_path, top, wanted, headful, min_delay, max_delay))


async def _run(input_path, db_path, top, sites, headful, min_delay, max_delay):
    queries = _load_products(input_path)
    log.info("Loaded %d products from %s", len(queries), input_path)

    repo = SqliteProductRepository(db_path)

    async with RateLimitedFetcher(
        headless=not headful, min_delay=min_delay, max_delay=max_delay
    ) as fetcher:
        source = CrawlerSource(fetcher, site_names=sites)
        use_case = TrackPricesUseCase(sources=[source], repository=repo)
        await use_case.execute(queries, top_per_source=top)

    log.info("Done. DB at %s", db_path)
