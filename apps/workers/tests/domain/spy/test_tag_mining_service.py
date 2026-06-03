"""TagMiningService — cross-marketplace tag aggregator."""

from __future__ import annotations

from datetime import UTC, datetime

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
from scalemyprints.domain.spy.search_service import SpySearchService
from scalemyprints.domain.spy.tag_mining_service import TagMiningService


class _FakeAdapter(SpyMarketplaceAdapter):
    def __init__(self, marketplace: Marketplace, listings: list[Listing]) -> None:
        self._marketplace = marketplace
        self._listings = listings

    @property
    def marketplace(self) -> Marketplace:
        return self._marketplace

    async def search(self, query, *, limit=20):
        return MarketplaceSearchResult(
            marketplace=self._marketplace,
            listings=self._listings[:limit],
        )

    async def fetch_listing(self, external_id: str) -> ListingDetailResult:
        return ListingDetailResult(error="not_implemented")

    async def fetch_shop(self, handle_or_id: str, *, depth=ShopAuditDepth.STANDARD):
        return ShopFetchResult()


def _listing(mkt: Marketplace, eid: str, tags: list[str]) -> Listing:
    now = datetime.now(UTC)
    return Listing(
        marketplace=mkt,
        external_id=eid,
        url=f"https://example.com/{mkt.value}/{eid}",  # type: ignore[arg-type]
        title=f"{mkt.value} {eid}",
        tags=tags,
        status=ListingStatus.ACTIVE,
        velocity_class=VelocityClass.STEADY,
        first_seen_at=now,
        last_seen_at=now,
    )


@pytest.mark.asyncio
async def test_aggregates_across_marketplaces() -> None:
    etsy = _FakeAdapter(
        Marketplace.ETSY,
        [
            _listing(Marketplace.ETSY, "e1", ["mom", "gift", "vintage"]),
            _listing(Marketplace.ETSY, "e2", ["mom", "funny"]),
        ],
    )
    redbubble = _FakeAdapter(
        Marketplace.REDBUBBLE,
        [_listing(Marketplace.REDBUBBLE, "r1", ["mom", "vintage", "retro"])],
    )
    search = SpySearchService(adapters=[etsy, redbubble])
    svc = TagMiningService(search_service=search)

    result = await svc.mine(seed="mom shirt")
    tag_map = {t.tag: t for t in result.tags}
    assert "mom" in tag_map
    assert tag_map["mom"].total_count == 3
    assert tag_map["mom"].distinct_marketplaces == 2
    assert "etsy" in tag_map["mom"].by_marketplace
    assert "redbubble" in tag_map["mom"].by_marketplace

    assert tag_map["vintage"].total_count == 2
    assert tag_map["funny"].total_count == 1


@pytest.mark.asyncio
async def test_normalizes_case_and_whitespace() -> None:
    etsy = _FakeAdapter(
        Marketplace.ETSY,
        [
            _listing(Marketplace.ETSY, "1", ["Mom", "  MOM ", "mom"]),
        ],
    )
    search = SpySearchService(adapters=[etsy])
    svc = TagMiningService(search_service=search)
    result = await svc.mine(seed="x")
    tag_map = {t.tag: t for t in result.tags}
    assert "mom" in tag_map
    assert tag_map["mom"].total_count == 3


@pytest.mark.asyncio
async def test_empty_listings_returns_empty() -> None:
    search = SpySearchService(adapters=[])
    svc = TagMiningService(search_service=search)
    result = await svc.mine(seed="anything")
    assert result.tags == []
    assert result.total_listings_scanned == 0
