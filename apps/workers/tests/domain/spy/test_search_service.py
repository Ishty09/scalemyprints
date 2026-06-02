"""SpySearchService — fan-out + merge + persistence behavior."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from scalemyprints.domain.spy.enums import (
    ListingStatus,
    Marketplace,
    ShopAuditDepth,
    VelocityClass,
)
from scalemyprints.domain.spy.models import Listing, SpyQuery
from scalemyprints.domain.spy.ports import (
    ListingDetailResult,
    MarketplaceSearchResult,
    ShopFetchResult,
    SpyMarketplaceAdapter,
)
from scalemyprints.domain.spy.search_service import SpySearchService
from scalemyprints.infrastructure.spy_storage.memory_listing_store import (
    MemoryListingStore,
)


class _FakeAdapter(SpyMarketplaceAdapter):
    def __init__(
        self,
        marketplace: Marketplace,
        *,
        listings: list[Listing] | None = None,
        error: str | None = None,
        raises: BaseException | None = None,
    ) -> None:
        self._marketplace = marketplace
        self._listings = listings or []
        self._error = error
        self._raises = raises

    @property
    def marketplace(self) -> Marketplace:
        return self._marketplace

    async def search(
        self,
        query: SpyQuery,
        *,
        limit: int = 20,
    ) -> MarketplaceSearchResult:
        if self._raises:
            raise self._raises
        return MarketplaceSearchResult(
            marketplace=self._marketplace,
            listings=self._listings[:limit],
            error=self._error,
        )

    async def fetch_listing(self, external_id: str) -> ListingDetailResult:
        return ListingDetailResult(error="not_implemented_in_test")

    async def fetch_shop(
        self,
        handle_or_id: str,
        *,
        depth: ShopAuditDepth = ShopAuditDepth.STANDARD,
    ) -> ShopFetchResult:
        return ShopFetchResult(error="not_implemented_in_test")


def _make_listing(marketplace: Marketplace, external_id: str) -> Listing:
    now = datetime.now(UTC)
    return Listing(
        marketplace=marketplace,
        external_id=external_id,
        url=f"https://example.com/{marketplace.value}/{external_id}",  # type: ignore[arg-type]
        title=f"{marketplace.value} listing {external_id}",
        status=ListingStatus.ACTIVE,
        velocity_class=VelocityClass.STEADY,
        first_seen_at=now,
        last_seen_at=now,
    )


@pytest.mark.asyncio
async def test_merges_results_across_marketplaces() -> None:
    etsy_a = _make_listing(Marketplace.ETSY, "1")
    redbubble_a = _make_listing(Marketplace.REDBUBBLE, "2")

    svc = SpySearchService(
        adapters=[
            _FakeAdapter(Marketplace.ETSY, listings=[etsy_a]),
            _FakeAdapter(Marketplace.REDBUBBLE, listings=[redbubble_a]),
        ],
    )
    result = await svc.run(SpyQuery(text="hello", limit=10))

    assert len(result.listings) == 2
    assert {l.marketplace for l in result.listings} == {Marketplace.ETSY, Marketplace.REDBUBBLE}
    assert set(result.sources_used) == {Marketplace.ETSY, Marketplace.REDBUBBLE}
    assert result.sources_failed == []


@pytest.mark.asyncio
async def test_records_failures_without_raising() -> None:
    etsy_a = _make_listing(Marketplace.ETSY, "1")
    svc = SpySearchService(
        adapters=[
            _FakeAdapter(Marketplace.ETSY, listings=[etsy_a]),
            _FakeAdapter(Marketplace.REDBUBBLE, error="http_403"),
            _FakeAdapter(Marketplace.AMAZON_MERCH, raises=RuntimeError("boom")),
        ],
    )
    result = await svc.run(SpyQuery(text="hello", limit=10))

    assert len(result.listings) == 1
    assert Marketplace.ETSY in result.sources_used
    assert any(m == Marketplace.REDBUBBLE for m, _ in result.sources_failed)
    assert any(m == Marketplace.AMAZON_MERCH for m, _ in result.sources_failed)


@pytest.mark.asyncio
async def test_filters_to_selected_marketplaces() -> None:
    svc = SpySearchService(
        adapters=[
            _FakeAdapter(
                Marketplace.ETSY,
                listings=[_make_listing(Marketplace.ETSY, "1")],
            ),
            _FakeAdapter(
                Marketplace.REDBUBBLE,
                listings=[_make_listing(Marketplace.REDBUBBLE, "2")],
            ),
        ],
    )
    result = await svc.run(
        SpyQuery(text="hello", marketplaces=[Marketplace.ETSY], limit=10),
    )

    assert len(result.listings) == 1
    assert result.listings[0].marketplace == Marketplace.ETSY


@pytest.mark.asyncio
async def test_persists_to_listing_store_best_effort() -> None:
    store = MemoryListingStore()
    svc = SpySearchService(
        adapters=[
            _FakeAdapter(
                Marketplace.ETSY,
                listings=[_make_listing(Marketplace.ETSY, "X1")],
            ),
        ],
        listing_store=store,
    )
    result = await svc.run(SpyQuery(text="hello"))
    assert result.listings
    assert store.size() == 1


@pytest.mark.asyncio
async def test_empty_adapter_list_returns_empty() -> None:
    svc = SpySearchService(adapters=[])
    result = await svc.run(SpyQuery(text="anything"))
    assert result.listings == []
    assert result.sources_used == []
