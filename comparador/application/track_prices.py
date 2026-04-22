import logging

from comparador.domain.identity import link_status_for_score
from comparador.domain.models import ProductQuery
from comparador.ports.price_source import PriceSource
from comparador.ports.repository import ProductRepository

log = logging.getLogger(__name__)


class TrackPricesUseCase:
    """For each product query, run all configured price sources and persist
    a price snapshot per marketplace listing found. History accumulates in
    the repository across runs.
    """

    def __init__(
        self, sources: list[PriceSource], repository: ProductRepository
    ) -> None:
        self._sources = sources
        self._repository = repository

    async def execute(
        self, queries: list[ProductQuery], top_per_source: int = 5
    ) -> None:
        for i, q in enumerate(queries, 1):
            log.info("[%d/%d] tracking: %s", i, len(queries), q.name)
            product = self._repository.upsert_product(q)

            for source in self._sources:
                try:
                    snaps = await source.search(q, max_results=top_per_source)
                except Exception as e:
                    log.warning(
                        "source '%s' failed on '%s': %s", source.name, q.name, e
                    )
                    continue

                for snap in snaps:
                    if link_status_for_score(snap.match_score) is None:
                        continue  # score too low, skip persisting noise
                    listing = self._repository.upsert_listing(product, snap)
                    self._repository.add_price_snapshot(listing, snap)
                    log.info(
                        "  %s/%s [%s] R$ %s match=%.0f — %s",
                        snap.site,
                        snap.site_id,
                        listing.link_status,
                        f"{snap.price:.2f}" if snap.price is not None else "—",
                        snap.match_score,
                        snap.title[:60],
                    )
