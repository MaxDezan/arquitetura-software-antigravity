import logging

from comparador.adapters.sources.crawler.fetcher import RateLimitedFetcher
from comparador.adapters.sources.crawler.matcher import rank_results
from comparador.adapters.sources.crawler.sites.amazon import AmazonScraper
from comparador.adapters.sources.crawler.sites.magalu import MagaluScraper
from comparador.adapters.sources.crawler.sites.mercadolivre import MercadoLivreScraper
from comparador.domain.models import ListingSnapshot, ProductQuery
from comparador.ports.price_source import PriceSource

log = logging.getLogger(__name__)


SITES = {
    "mercadolivre": MercadoLivreScraper,
    "amazon": AmazonScraper,
    "magalu": MagaluScraper,
}


class CrawlerSource(PriceSource):
    """PriceSource adapter that aggregates site-specific scrapers."""

    name = "crawler"

    def __init__(self, fetcher: RateLimitedFetcher, site_names: list[str]) -> None:
        self._scrapers = [SITES[n](fetcher) for n in site_names if n in SITES]

    async def search(
        self, query: ProductQuery, max_results: int = 5
    ) -> list[ListingSnapshot]:
        search_term = query.reference_model or query.name
        out: list[ListingSnapshot] = []
        for scraper in self._scrapers:
            try:
                raw = await scraper.search(search_term, max_results=max_results * 2)
            except Exception as e:
                log.warning(
                    "%s failed on '%s': %s: %s",
                    scraper.name, query.name, type(e).__name__, e,
                )
                continue
            ranked = rank_results(query.name, raw)
            out.extend(ranked[:max_results])
        return out
