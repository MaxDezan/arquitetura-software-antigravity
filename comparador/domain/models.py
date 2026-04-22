from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import UUID


AUTO_LINK_THRESHOLD = 85.0
MANUAL_REVIEW_THRESHOLD = 55.0


@dataclass
class ProductQuery:
    """User-facing request: track this product."""

    name: str
    reference_model: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class ListingSnapshot:
    """Transient observation returned by a PriceSource adapter.

    Contains everything needed to persist one price point for a specific
    marketplace listing. `site_id` must be stable across runs so historical
    comparison works — extracted from URL (MLB/ASIN/SKU).
    """

    site: str
    site_id: str
    title: str
    url: str
    price: Optional[float]
    original_price: Optional[float] = None
    currency: str = "BRL"
    seller: Optional[str] = None
    image_url: Optional[str] = None
    rating: Optional[float] = None
    reviews_count: Optional[int] = None
    availability: Optional[str] = None
    match_score: float = 0.0
    fetched_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Product:
    id: UUID
    name: str                       # canonical, used for dedup
    display_name: str               # as entered by user
    reference_model: Optional[str]
    notes: Optional[str]
    created_at: datetime


@dataclass
class Listing:
    id: UUID
    product_id: UUID
    site: str
    site_id: str
    title: str
    url: str
    seller: Optional[str]
    image_url: Optional[str]
    match_score: float
    link_status: str                # 'auto' | 'pending' | 'confirmed' | 'rejected'
    first_seen_at: datetime
    last_seen_at: datetime


@dataclass
class PriceSnapshot:
    listing_id: UUID
    price: Optional[float]
    original_price: Optional[float]
    currency: str
    availability: Optional[str]
    fetched_at: datetime
