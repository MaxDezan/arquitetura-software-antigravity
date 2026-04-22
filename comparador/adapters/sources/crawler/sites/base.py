from abc import ABC, abstractmethod

from comparador.adapters.sources.crawler.fetcher import RateLimitedFetcher
from comparador.domain.models import ListingSnapshot


class BaseScraper(ABC):
    name: str = ""
    domain: str = ""

    def __init__(self, fetcher: RateLimitedFetcher) -> None:
        self.fetcher = fetcher

    @abstractmethod
    async def search(
        self, query: str, max_results: int = 5
    ) -> list[ListingSnapshot]: ...
