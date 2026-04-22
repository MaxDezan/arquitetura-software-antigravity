from abc import ABC, abstractmethod

from comparador.domain.models import ListingSnapshot, ProductQuery


class PriceSource(ABC):
    """Outbound port — any price source (crawler, official API, importer)
    implements this. The application layer only depends on this contract.
    """

    name: str = ""

    @abstractmethod
    async def search(
        self, query: ProductQuery, max_results: int = 5
    ) -> list[ListingSnapshot]:
        """Return listings matching the query, with match_score populated."""
