"""VelocityRefreshService — batched re-fetch + re-classify."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from scalemyprints.domain.spy.enums import (
    ListingStatus,
    Marketplace,
    ShopAuditDepth,
    VelocityClass,
)
from scalemyprints.domain.spy.models import Listing
from scalemyprints.domain.spy.ports import (
    ListingDetailResult,
    MarketplaceSearchResult,
    ShopFetchResult,
    SpyMarketplaceAdapter,
)
from scalemyprints.domain.spy.velocity_refresh_service import VelocityRefreshService
from scalemyprints.domain.spy.velocity_service import VelocityAnalyzer
from scalemyprints.infrastructure.spy_storage.memory_listing_store import (
    MemoryListingStore,
)


class _FakeAdapter(SpyMarketplaceAdapter):
    def __init__(
        self,
        marketplace: Marketplace,
        *,
        fresh: Listing | None = None,
        error: str | None = None,
    ) -> None:
        self._marketplace = marketplace
        self._fresh = fresh
        self._error = error

    @property
    def marketplace(self) -> Marketplace:
        return self._marketplace

    async def search(self, query, *, limit=20):
        return MarketplaceSearchResult(marketplace=self._marketplace)

    async def fetch_listing(self, external_id: str) -> ListingDetailResult:
        return ListingDetailResult(listing=self._fresh, error=self._error)

    async def fetch_shop(self, handle_or_id: str, *, depth=ShopAuditDepth.STANDARD):
        return ShopFetchResult()


def _l(external_id: str, *, reviews: int) -> Listing:
    now = datetime.now(UTC)
    return Listing(
        marketplace=Marketplace.ETSY,
        external_id=external_id,
        url=f"https://etsy.com/listing/{external_id}",  # type: ignore[arg-type]
        title="x",
        reviews_count=reviews,
        status=ListingStatus.ACTIVE,
        velocity_class=VelocityClass.STEADY,
        first_seen_at=now - timedelta(days=30),
        last_seen_at=now - timedelta(days=10),
    )


@pytest.mark.asyncio
async def test_empty_candidates_returns_zero_counts() -> None:
    svc = VelocityRefreshService(
        adapters=[],
        listing_store=MemoryListingStore(),
        analyzer=VelocityAnalyzer(),
    )
    summary = await svc.refresh([])
    assert summary.candidates == 0
    assert summary.refreshed == 0


@pytest.mark.asyncio
async def test_unsupported_marketplace_is_failure() -> None:
    store = MemoryListingStore()
    listing = _l("X1", reviews=10)
    listing_id = await store.upsert_listing(listing)
    svc = VelocityRefreshService(
        adapters=[],
        listing_store=store,
        analyzer=VelocityAnalyzer(),
    )
    summary = await svc.refresh([(listing_id, listing)])
    assert summary.refreshed == 0
    assert summary.failed == 1


@pytest.mark.asyncio
async def test_adapter_error_counted_as_failure() -> None:
    store = MemoryListingStore()
    listing = _l("X1", reviews=10)
    listing_id = await store.upsert_listing(listing)
    svc = VelocityRefreshService(
        adapters=[_FakeAdapter(Marketplace.ETSY, error="http_403")],
        listing_store=store,
        analyzer=VelocityAnalyzer(),
    )
    summary = await svc.refresh([(listing_id, listing)])
    assert summary.failed == 1
    assert any("http_403" in e for e in summary.errors)


@pytest.mark.asyncio
async def test_happy_path_increments_refreshed() -> None:
    store = MemoryListingStore()
    listing = _l("X1", reviews=10)
    listing_id = await store.upsert_listing(listing)
    fresh = _l("X1", reviews=20)
    svc = VelocityRefreshService(
        adapters=[_FakeAdapter(Marketplace.ETSY, fresh=fresh)],
        listing_store=store,
        analyzer=VelocityAnalyzer(),
    )
    summary = await svc.refresh([(listing_id, listing)])
    assert summary.refreshed == 1
    assert summary.failed == 0
    assert summary.by_marketplace.get("etsy") == 1
