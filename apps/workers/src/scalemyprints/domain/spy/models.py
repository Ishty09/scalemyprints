"""
Spy — domain models.

All models frozen (immutable). Pure data shapes; no behavior.
Behavior lives in services (search_service, velocity_service,
reverse_image_service, shop_audit_service, viral_mining_service).

Keep these in sync with packages/contracts/src/spy.ts and the
spy_* tables in infra/supabase/migrations/.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from scalemyprints.domain.spy.enums import (
    ImageMatchType,
    ListingStatus,
    Marketplace,
    SaturationClass,
    ShopAuditDepth,
    SpyFailureReason,
    SpyJobStatus,
    VelocityClass,
    ViralSource,
)

# Bounded numeric types
SpyScore = Annotated[int, Field(ge=0, le=100)]
NonNegativeInt = Annotated[int, Field(ge=0)]
NonNegativeFloat = Annotated[float, Field(ge=0.0)]


# -----------------------------------------------------------------------------
# Listing — the central object: a single product on a marketplace
# -----------------------------------------------------------------------------


class Listing(BaseModel):
    """
    Canonical record for a tracked listing on any marketplace.

    Identified by `(marketplace, external_id)`. The full URL is stored
    for back-links; thumbnail / image URLs are normalized to https.
    """

    model_config = ConfigDict(frozen=True)

    marketplace: Marketplace
    external_id: str                       # platform's product id / sku / listing id
    url: HttpUrl
    title: str
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    price_usd: NonNegativeFloat | None = None
    currency: str | None = None            # original currency code
    thumbnail_url: HttpUrl | None = None
    image_urls: list[HttpUrl] = Field(default_factory=list)
    shop_external_id: str | None = None
    shop_handle: str | None = None
    shop_url: HttpUrl | None = None
    status: ListingStatus = ListingStatus.ACTIVE

    # Marketplace-reported stats (when available)
    favorites: NonNegativeInt | None = None       # Etsy heart count
    reviews_count: NonNegativeInt | None = None
    rating: float | None = Field(default=None, ge=0.0, le=5.0)

    # Our derived signals (filled in by services / latest snapshot)
    est_daily_sales: NonNegativeFloat | None = None
    velocity_class: VelocityClass = VelocityClass.STEADY

    first_seen_at: datetime
    last_seen_at: datetime


# -----------------------------------------------------------------------------
# Snapshot — timeseries entry for velocity / spike detection
# -----------------------------------------------------------------------------


class ListingSnapshot(BaseModel):
    """One sample of a listing's state at a moment in time."""

    model_config = ConfigDict(frozen=True)

    listing_id: str                                       # FK to spy_listings
    captured_at: datetime
    price_usd: NonNegativeFloat | None = None
    favorites: NonNegativeInt | None = None
    reviews_count: NonNegativeInt | None = None
    rating: float | None = Field(default=None, ge=0.0, le=5.0)
    est_daily_sales: NonNegativeFloat | None = None
    rank_within_query: NonNegativeInt | None = None       # if found via a tracked query
    raw_payload: dict[str, object] | None = None          # adapter-specific blob


# -----------------------------------------------------------------------------
# Design embeddings — for reverse image search
# -----------------------------------------------------------------------------


class DesignEmbedding(BaseModel):
    """
    Per-image perceptual representations for similarity search.

    Each artwork (one of N images on a listing) gets its own row keyed
    by SHA-256 of the source bytes. Multiple listings can share the same
    embedding row when they re-use identical artwork.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    sha256: str = Field(min_length=64, max_length=64)
    phash: int                                             # 64-bit perceptual hash
    clip_embedding: list[float] = Field(min_length=512)    # CLIP ViT-L/14 = 768; ViT-B/32 = 512+
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    bytes_size: NonNegativeInt
    source_url: HttpUrl | None = None
    created_at: datetime


class ReverseImageMatch(BaseModel):
    """One match returned by reverse image search."""

    model_config = ConfigDict(frozen=True)

    listing: Listing
    match_type: ImageMatchType
    phash_distance: NonNegativeInt | None = None           # 0-64 Hamming
    clip_cosine: float | None = Field(default=None, ge=-1.0, le=1.0)
    score: SpyScore                                        # combined 0-100


# -----------------------------------------------------------------------------
# Shop teardown
# -----------------------------------------------------------------------------


class ShopProfile(BaseModel):
    """Persisted shop metadata across crawls."""

    model_config = ConfigDict(frozen=True)

    marketplace: Marketplace
    external_id: str
    handle: str
    display_name: str | None = None
    url: HttpUrl
    location: str | None = None
    joined_year: int | None = Field(default=None, ge=1990, le=3000)
    total_sales: NonNegativeInt | None = None
    listings_count: NonNegativeInt | None = None
    avg_review_rating: float | None = Field(default=None, ge=0.0, le=5.0)
    reviews_count: NonNegativeInt | None = None
    first_seen_at: datetime
    last_seen_at: datetime


class ShopAuditReport(BaseModel):
    """Result of `shop_audit_service.run()` — a forensic report."""

    model_config = ConfigDict(frozen=True)

    shop: ShopProfile
    depth: ShopAuditDepth
    listings_sampled: NonNegativeInt
    est_monthly_revenue_usd: NonNegativeFloat | None = None
    top_listings: list[Listing] = Field(default_factory=list)
    most_used_tags: list[tuple[str, int]] = Field(default_factory=list)  # (tag, count)
    avg_price_usd: NonNegativeFloat | None = None
    new_listings_last_30d: NonNegativeInt | None = None
    restock_cadence_days: float | None = Field(default=None, ge=0.0)
    captured_at: datetime
    error: str | None = None


# -----------------------------------------------------------------------------
# Velocity signal — emitted when a listing crosses a spike threshold
# -----------------------------------------------------------------------------


class VelocitySignal(BaseModel):
    """A spike-worthy event detected on a listing's snapshot series."""

    model_config = ConfigDict(frozen=True)

    listing_id: str
    captured_at: datetime
    velocity_class: VelocityClass
    z_score: float                                         # vs 7-day baseline
    sales_baseline: NonNegativeFloat | None = None
    sales_current: NonNegativeFloat | None = None
    favorites_delta_7d: int | None = None                  # signed
    reviews_delta_7d: int | None = None
    saturation_class: SaturationClass | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    note: str | None = None                                # human-readable summary


# -----------------------------------------------------------------------------
# Viral signal — a trend candidate from upstream sources
# -----------------------------------------------------------------------------


class ViralSignal(BaseModel):
    """
    A trending phrase / meme / quote harvested from non-marketplace sources.

    We score `pod_readiness` so the UI can filter to "things that would
    become POD products" vs random viral noise.
    """

    model_config = ConfigDict(frozen=True)

    source: ViralSource
    source_url: HttpUrl | None = None
    phrase: str = Field(min_length=2, max_length=400)
    detected_at: datetime
    engagement: NonNegativeInt = 0                         # likes / upvotes / views
    momentum_score: SpyScore                               # 0-100, our calc
    pod_readiness_score: SpyScore                          # 0-100, LLM-classified
    existing_pod_count: NonNegativeInt = 0                 # how many POD listings already use phrase
    suggested_styles: list[str] = Field(default_factory=list)
    note: str | None = None


# -----------------------------------------------------------------------------
# Spy query — user-facing search request
# -----------------------------------------------------------------------------


class SpyQuery(BaseModel):
    """User-facing search query (text or URL)."""

    model_config = ConfigDict(frozen=True)

    text: str | None = Field(default=None, max_length=200)
    listing_url: HttpUrl | None = None
    marketplaces: list[Marketplace] = Field(default_factory=list)  # empty = all
    limit: int = Field(default=20, ge=1, le=100)


class SpySearchResult(BaseModel):
    """Combined result returned by `search_service.run()`."""

    model_config = ConfigDict(frozen=True)

    query: SpyQuery
    listings: list[Listing] = Field(default_factory=list)
    sources_used: list[Marketplace] = Field(default_factory=list)
    sources_failed: list[tuple[Marketplace, str]] = Field(default_factory=list)
    duration_ms: NonNegativeInt = 0


# -----------------------------------------------------------------------------
# Spy job — async work envelope (reverse-image, shop-audit, viral-scan)
# -----------------------------------------------------------------------------


class SpyJob(BaseModel):
    """Persisted lifecycle of an async Spy job."""

    model_config = ConfigDict(frozen=True)

    id: str
    user_id: str
    kind: str                                              # "reverse_image" | "shop_audit" | "viral_scan"
    status: SpyJobStatus
    request_payload: dict[str, object]
    result_payload: dict[str, object] | None = None
    failure_reason: SpyFailureReason | None = None
    failure_message: str | None = None
    sources_attempted: list[str] = Field(default_factory=list)
    sources_succeeded: list[str] = Field(default_factory=list)
    duration_ms: NonNegativeInt = 0
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
