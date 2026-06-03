"""
Spy — request/response DTOs.

Mirror packages/contracts/src/spy.ts on the TypeScript side. Stays
deliberately thin: re-uses domain Pydantic models where possible.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

if TYPE_CHECKING:
    from scalemyprints.domain.spy.enums import (
        ImageMatchType,
        ListingStatus,
        Marketplace,
        VelocityClass,
    )
    from scalemyprints.domain.spy.models import (
        Listing,
        ReverseImageMatch,
        SpySearchResult,
    )

# ---------------------------------------------------------------------------
# POST /api/v1/spy/search
# ---------------------------------------------------------------------------


class SpySearchBody(BaseModel):
    """Body for POST /api/v1/spy/search."""

    model_config = ConfigDict(extra="forbid")

    text: str | None = Field(default=None, max_length=200)
    listing_url: HttpUrl | None = None
    marketplaces: list[Marketplace] = Field(default_factory=list)
    limit: int = Field(default=20, ge=1, le=100)


class SpyListingItem(BaseModel):
    """Public listing shape (one row in a search response)."""

    model_config = ConfigDict(extra="forbid")

    marketplace: Marketplace
    external_id: str
    url: HttpUrl
    title: str
    description: str | None
    tags: list[str]
    price_usd: float | None
    currency: str | None
    thumbnail_url: HttpUrl | None
    shop_handle: str | None
    shop_url: HttpUrl | None
    status: ListingStatus
    favorites: int | None
    reviews_count: int | None
    rating: float | None
    est_daily_sales: float | None
    velocity_class: VelocityClass
    first_seen_at: datetime
    last_seen_at: datetime

    @classmethod
    def from_domain(cls, listing: Listing) -> SpyListingItem:
        return cls(
            marketplace=listing.marketplace,
            external_id=listing.external_id,
            url=listing.url,
            title=listing.title,
            description=listing.description,
            tags=listing.tags,
            price_usd=listing.price_usd,
            currency=listing.currency,
            thumbnail_url=listing.thumbnail_url,
            shop_handle=listing.shop_handle,
            shop_url=listing.shop_url,
            status=listing.status,
            favorites=listing.favorites,
            reviews_count=listing.reviews_count,
            rating=listing.rating,
            est_daily_sales=listing.est_daily_sales,
            velocity_class=listing.velocity_class,
            first_seen_at=listing.first_seen_at,
            last_seen_at=listing.last_seen_at,
        )


class SpySourceFailure(BaseModel):
    """One adapter that errored during a fan-out search."""

    model_config = ConfigDict(extra="forbid")

    marketplace: Marketplace
    error: str


class SpySearchResponse(BaseModel):
    """Combined response for POST /api/v1/spy/search."""

    model_config = ConfigDict(extra="forbid")

    listings: list[SpyListingItem]
    sources_used: list[Marketplace]
    sources_failed: list[SpySourceFailure]
    total: int
    duration_ms: int

    @classmethod
    def from_domain(cls, result: SpySearchResult) -> SpySearchResponse:
        return cls(
            listings=[SpyListingItem.from_domain(l) for l in result.listings],
            sources_used=result.sources_used,
            sources_failed=[
                SpySourceFailure(marketplace=m, error=e) for m, e in result.sources_failed
            ],
            total=len(result.listings),
            duration_ms=result.duration_ms,
        )


# ---------------------------------------------------------------------------
# POST /api/v1/spy/reverse-image  (multipart/form-data)
# ---------------------------------------------------------------------------


class ReverseImageMatchItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    listing: SpyListingItem
    match_type: ImageMatchType
    phash_distance: int | None
    clip_cosine: float | None
    score: int

    @classmethod
    def from_domain(cls, match: ReverseImageMatch) -> ReverseImageMatchItem:
        return cls(
            listing=SpyListingItem.from_domain(match.listing),
            match_type=match.match_type,
            phash_distance=match.phash_distance,
            clip_cosine=match.clip_cosine,
            score=match.score,
        )


class ReverseImageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_sha256: str
    matches: list[ReverseImageMatchItem]
    total: int
    duration_ms: int
    error: str | None = None


# ---------------------------------------------------------------------------
# GET /api/v1/spy/feed (hot movers)
# ---------------------------------------------------------------------------


class HotMoverItem(BaseModel):
    """A row from the `spy_hot_movers` view."""

    model_config = ConfigDict(extra="forbid")

    id: str
    marketplace: Marketplace
    title: str
    url: HttpUrl
    thumbnail_url: HttpUrl | None
    shop_handle: str | None
    shop_url: HttpUrl | None
    velocity_class: VelocityClass
    est_daily_sales: float | None
    price_usd: float | None
    favorites: int | None
    reviews_count: int | None
    last_seen_at: datetime


class HotMoversResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[HotMoverItem]
    total: int


# ---------------------------------------------------------------------------
# GET /api/v1/spy/shop/{marketplace}/{handle}
# ---------------------------------------------------------------------------


class ShopProfileItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    marketplace: Marketplace
    handle: str
    display_name: str | None
    url: HttpUrl
    location: str | None
    total_sales: int | None
    listings_count: int | None
    avg_review_rating: float | None
    reviews_count: int | None
    last_seen_at: datetime


# ---------------------------------------------------------------------------
# POST /api/v1/spy/shop-audit
# ---------------------------------------------------------------------------


class ShopAuditBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    marketplace: Marketplace
    handle: str = Field(min_length=1, max_length=120)
    depth: str = Field(default="standard", pattern="^(shallow|standard|deep)$")


class TagFrequencyItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tag: str
    count: int = Field(ge=0)


class ShopAuditResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shop: ShopProfileItem
    depth: str
    listings_sampled: int = Field(ge=0)
    est_monthly_revenue_usd: float | None
    avg_price_usd: float | None
    new_listings_last_30d: int | None
    restock_cadence_days: float | None
    top_listings: list[SpyListingItem]
    most_used_tags: list[TagFrequencyItem]
    captured_at: datetime
    error: str | None = None


# ---------------------------------------------------------------------------
# POST /api/v1/spy/saturation
# ---------------------------------------------------------------------------


class SaturationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phrase: str | None = Field(default=None, max_length=200)
    listing_ids: list[str] = Field(default_factory=list)
    marketplaces: list[Marketplace] = Field(default_factory=list)
    use_live_search: bool = True


class SaturationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: int = Field(ge=0, le=100)
    saturation_class: str
    listings_count: int
    unique_shops: int
    hhi: float
    gmv_pool_usd: float
    density_component: int
    concentration_component: int
    velocity_component: int
    recency_component: int
    explanation: str


# ---------------------------------------------------------------------------
# POST /api/v1/spy/profit
# ---------------------------------------------------------------------------


class ProfitBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    marketplace: Marketplace
    product_type: str = Field(min_length=1, max_length=40)
    sale_price_usd: float = Field(gt=0)
    printer: str = Field(default="printify", min_length=1)
    shipping_usd: float = Field(default=0.0, ge=0.0)
    ad_cpc_usd: float = Field(default=0.0, ge=0.0)
    ad_conversion_rate: float = Field(default=0.0, ge=0.0, le=1.0)


class ProfitResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sale_price_usd: float
    base_cost_usd: float
    marketplace_fee_usd: float
    shipping_usd: float
    ad_cost_usd: float
    profit_usd: float
    margin_pct: float
    printer: str
    note: str | None = None


# ---------------------------------------------------------------------------
# GET /api/v1/spy/ads
# ---------------------------------------------------------------------------


class AdSpyHitItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform: str
    ad_id: str
    page_or_handle: str
    page_id: str | None
    primary_text: str | None
    cta: str | None
    landing_url: HttpUrl | None
    started_at: datetime | None
    last_seen_at: datetime | None
    impressions_lower: int | None
    impressions_upper: int | None
    countries: list[str]


class AdLibraryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform: str
    hits: list[AdSpyHitItem]
    total: int
    duration_ms: int
    error: str | None = None


# ---------------------------------------------------------------------------
# POST /api/v1/spy/_internal/refresh-velocity  (cron-only)
# ---------------------------------------------------------------------------


class VelocityRefreshBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=50, ge=1, le=500)
    max_age_hours: int = Field(default=6, ge=1, le=168)


class VelocityRefreshResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    started_at: datetime
    completed_at: datetime
    duration_ms: int
    candidates: int
    refreshed: int
    failed: int
    spikes_detected: int
    by_marketplace: dict[str, int]
    errors: list[str]
    reviews_count: int | None
    last_seen_at: datetime
