from abc import ABC, abstractmethod
from typing import Optional
from uuid import UUID

from comparador.domain.models import (
    Listing,
    ListingSnapshot,
    Product,
    ProductQuery,
)


class ProductRepository(ABC):
    """Outbound port for persistence. Commands + queries grouped for MVP."""

    # ---- commands ----
    @abstractmethod
    def upsert_product(self, query: ProductQuery) -> Product: ...

    @abstractmethod
    def upsert_listing(self, product: Product, snap: ListingSnapshot) -> Listing: ...

    @abstractmethod
    def add_price_snapshot(self, listing: Listing, snap: ListingSnapshot) -> None: ...

    @abstractmethod
    def set_listing_status(self, listing_id: UUID, status: str) -> None: ...

    # ---- queries (for dashboard) ----
    @abstractmethod
    def list_products_summary(self) -> list[dict]: ...

    @abstractmethod
    def get_product(self, product_id: UUID) -> Optional[Product]: ...

    @abstractmethod
    def get_listings_with_current_price(self, product_id: UUID) -> list[dict]: ...

    @abstractmethod
    def get_price_history(self, product_id: UUID) -> dict[str, list[dict]]: ...

    # ---- queries (public) ----
    @abstractmethod
    def list_products_public_view(self) -> list[dict]: ...

    @abstractmethod
    def get_listings_for_comparison(self, product_id: UUID) -> list[dict]: ...
