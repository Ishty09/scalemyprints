"""
Spy — ports (Protocol interfaces).

Domain depends on these Protocols, never on concrete adapters.

Adapters MUST NOT raise. On failure they return a Result object whose
`error` field is set. The orchestrator decides whether to retry,
escalate, or continue with partial data.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from scalemyprints.domain.spy.enums import (
    Marketplace,
    ShopAuditDepth,
    SpyFailureReason,
    ViralSource,
)
from scalemyprints.domain.spy.models import (  # noqa: TC001
    DesignEmbedding,
    Listing,
    ListingSnapshot,
    ReverseImageMatch,
    ShopAuditReport,
    ShopProfile,
    SpyQuery,
    VelocitySignal,
    ViralSignal,
)

# -----------------------------------------------------------------------------
# Result envelopes
# -----------------------------------------------------------------------------


class MarketplaceSearchResult(BaseModel):
    """Search payload returned by a per-marketplace adapter."""

    model_config = ConfigDict(frozen=True)

    marketplace: Marketplace
    listings: list[Listing] = Field(default_factory=list)
    duration_ms: int = 0
    error: str | None = None
    failure_reason: SpyFailureReason | None = None


class ListingDetailResult(BaseModel):
    """Detail-fetch result for a single listing (used by reverse search enrich)."""

    model_config = ConfigDict(frozen=True)

    listing: Listing | None = None
    snapshot: ListingSnapshot | None = None
    duration_ms: int = 0
    error: str | None = None


class ShopFetchResult(BaseModel):
    """Result of fetching a shop profile from an adapter."""

    model_config = ConfigDict(frozen=True)

    profile: ShopProfile | None = None
    listings: list[Listing] = Field(default_factory=list)
    duration_ms: int = 0
    error: str | None = None


class ImageDownloadResult(BaseModel):
    """An image fetched from a URL — bytes + content-type."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    image_bytes: bytes
    content_type: str
    bytes_size: int = Field(ge=1)
    source_url: HttpUrl
    error: str | None = None


class EmbeddingResult(BaseModel):
    """Output of `ImageEmbedder.embed()`."""

    model_config = ConfigDict(frozen=True)

    sha256: str
    phash: int
    clip_embedding: list[float] = Field(min_length=128)
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    bytes_size: int = Field(ge=1)
    duration_ms: int = 0
    error: str | None = None


class EmbeddingSearchHit(BaseModel):
    """One hit returned by the embedding store ANN search."""

    model_config = ConfigDict(frozen=True)

    sha256: str
    listing_ids: list[str] = Field(default_factory=list)
    phash_distance: int | None = None
    clip_cosine: float | None = None


# -----------------------------------------------------------------------------
# Marketplace adapter — search + detail + shop fetch
# -----------------------------------------------------------------------------


@runtime_checkable
class SpyMarketplaceAdapter(Protocol):
    """
    Source of listings + shop profiles for one marketplace.

    Adapters never raise. On failure they return a result whose
    `error` field is set. The orchestrator escalates.
    """

    @property
    def marketplace(self) -> Marketplace: ...

    async def search(
        self,
        query: SpyQuery,
        *,
        limit: int = 20,
    ) -> MarketplaceSearchResult: ...

    async def fetch_listing(
        self,
        external_id: str,
    ) -> ListingDetailResult: ...

    async def fetch_shop(
        self,
        handle_or_id: str,
        *,
        depth: ShopAuditDepth = ShopAuditDepth.STANDARD,
    ) -> ShopFetchResult: ...


# -----------------------------------------------------------------------------
# Image pipeline — download → embed → store
# -----------------------------------------------------------------------------


@runtime_checkable
class ImageDownloader(Protocol):
    """Downloads an image from a URL. Honors anti-bot best-effort."""

    async def download(self, url: str) -> ImageDownloadResult: ...


@runtime_checkable
class ImageEmbedder(Protocol):
    """Turns image bytes into a (phash, CLIP vector) pair."""

    @property
    def embedding_dim(self) -> int: ...

    async def embed(self, image_bytes: bytes) -> EmbeddingResult: ...


@runtime_checkable
class EmbeddingStore(Protocol):
    """
    Persisted vector store backing reverse image search.

    Concrete impls: Supabase pgvector (production), in-memory (tests).
    """

    async def upsert(self, embedding: DesignEmbedding) -> None: ...

    async def link_listing(
        self,
        sha256: str,
        listing_id: str,
    ) -> None: ...

    async def search_phash(
        self,
        phash: int,
        *,
        max_distance: int = 12,
        limit: int = 50,
    ) -> list[EmbeddingSearchHit]: ...

    async def search_clip(
        self,
        vector: list[float],
        *,
        min_cosine: float = 0.70,
        limit: int = 50,
    ) -> list[EmbeddingSearchHit]: ...


# -----------------------------------------------------------------------------
# Listing store — Supabase-backed persistence for listings + snapshots
# -----------------------------------------------------------------------------


@runtime_checkable
class ListingStore(Protocol):
    """Persists Listing + ListingSnapshot rows."""

    async def upsert_listing(self, listing: Listing) -> str: ...
    """Returns the spy_listings.id of the upserted row."""

    async def record_snapshot(self, snapshot: ListingSnapshot) -> None: ...

    async def get_listing(self, listing_id: str) -> Listing | None: ...

    async def get_by_external(
        self,
        marketplace: Marketplace,
        external_id: str,
    ) -> tuple[str, Listing] | None: ...
    """Returns (listing_id, Listing) or None."""

    async def recent_snapshots(
        self,
        listing_id: str,
        *,
        days: int = 14,
        limit: int = 200,
    ) -> list[ListingSnapshot]: ...

    async def candidates_for_refresh(
        self,
        *,
        limit: int = 100,
        max_age_hours: int = 6,
    ) -> list[tuple[str, Listing]]:
        """
        Return (listing_id, Listing) pairs that haven't been refreshed
        for at least `max_age_hours`. Used by the velocity refresh cron.
        """
        ...


# -----------------------------------------------------------------------------
# Velocity service port (so cron + API both call the same surface)
# -----------------------------------------------------------------------------


@runtime_checkable
class VelocityAnalyzer(Protocol):
    """Detects spikes from a series of snapshots."""

    async def analyze(
        self,
        listing_id: str,
        snapshots: list[ListingSnapshot],
    ) -> VelocitySignal | None: ...


# -----------------------------------------------------------------------------
# Shop audit
# -----------------------------------------------------------------------------


@runtime_checkable
class ShopAuditor(Protocol):
    """Runs forensic teardowns on a shop given its profile."""

    async def audit(
        self,
        marketplace: Marketplace,
        handle_or_id: str,
        *,
        depth: ShopAuditDepth = ShopAuditDepth.STANDARD,
    ) -> ShopAuditReport: ...


# -----------------------------------------------------------------------------
# Viral source adapter
# -----------------------------------------------------------------------------


class ViralFetchResult(BaseModel):
    """One viral-source pull."""

    model_config = ConfigDict(frozen=True)

    source: ViralSource
    signals: list[ViralSignal] = Field(default_factory=list)
    duration_ms: int = 0
    error: str | None = None


@runtime_checkable
class ViralSourceAdapter(Protocol):
    """Source of trending phrases / signals from a single platform."""

    @property
    def source(self) -> ViralSource: ...

    async def fetch(
        self,
        *,
        limit: int = 100,
    ) -> ViralFetchResult: ...


# -----------------------------------------------------------------------------
# Reverse image search service port (so the API layer can depend on it)
# -----------------------------------------------------------------------------


class ReverseImageSearchResult(BaseModel):
    """Final shape returned to API for a reverse image search."""

    model_config = ConfigDict(frozen=True)

    query_sha256: str
    matches: list[ReverseImageMatch] = Field(default_factory=list)
    duration_ms: int = 0
    error: str | None = None
    failure_reason: SpyFailureReason | None = None


@runtime_checkable
class ReverseImageSearcher(Protocol):
    """High-level: image_bytes → ReverseImageSearchResult."""

    async def search(
        self,
        image_bytes: bytes,
        *,
        limit: int = 30,
        min_clip_cosine: float = 0.70,
    ) -> ReverseImageSearchResult: ...
