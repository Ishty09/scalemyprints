"""ShopAuditService — pure analysis + adapter dispatch."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from scalemyprints.domain.spy.enums import (
    ListingStatus,
    Marketplace,
    ShopAuditDepth,
    VelocityClass,
)
from scalemyprints.domain.spy.models import Listing, ShopProfile
from scalemyprints.domain.spy.ports import (
    ListingDetailResult,
    MarketplaceSearchResult,
    ShopFetchResult,
    SpyMarketplaceAdapter,
)
from scalemyprints.domain.spy.shop_audit_service import ShopAuditService


class _FakeAdapter(SpyMarketplaceAdapter):
    def __init__(
        self,
        marketplace: Marketplace,
        *,
        profile: ShopProfile | None = None,
        listings: list[Listing] | None = None,
        error: str | None = None,
    ) -> None:
        self._marketplace = marketplace
        self._profile = profile
        self._listings = listings or []
        self._error = error

    @property
    def marketplace(self) -> Marketplace:
        return self._marketplace

    async def search(self, query, *, limit=20):
        return MarketplaceSearchResult(marketplace=self._marketplace)

    async def fetch_listing(self, external_id: str) -> ListingDetailResult:
        return ListingDetailResult(error="not_implemented_in_test")

    async def fetch_shop(self, handle_or_id: str, *, depth=ShopAuditDepth.STANDARD):
        return ShopFetchResult(
            profile=self._profile,
            listings=self._listings,
            error=self._error,
        )


def _listing(
    external_id: str,
    *,
    price: float = 19.99,
    eds: float = 1.0,
    tags: list[str] | None = None,
    favorites: int = 0,
    days_old: int = 60,
) -> Listing:
    now = datetime.now(UTC)
    first_seen = now - timedelta(days=days_old)
    return Listing(
        marketplace=Marketplace.ETSY,
        external_id=external_id,
        url=f"https://etsy.com/listing/{external_id}",  # type: ignore[arg-type]
        title=f"design {external_id}",
        tags=tags or [],
        price_usd=price,
        currency="USD",
        favorites=favorites,
        est_daily_sales=eds,
        status=ListingStatus.ACTIVE,
        velocity_class=VelocityClass.STEADY,
        first_seen_at=first_seen,
        last_seen_at=now,
    )


def _profile() -> ShopProfile:
    now = datetime.now(UTC)
    return ShopProfile(
        marketplace=Marketplace.ETSY,
        external_id="ShopA",
        handle="ShopA",
        display_name="Shop Alpha",
        url="https://etsy.com/shop/ShopA",  # type: ignore[arg-type]
        first_seen_at=now,
        last_seen_at=now,
    )


@pytest.mark.asyncio
async def test_no_listings_returns_zeroes() -> None:
    svc = ShopAuditService(
        adapters=[_FakeAdapter(Marketplace.ETSY, profile=_profile())],
    )
    report = await svc.audit(Marketplace.ETSY, "ShopA")
    assert report.error is None
    assert report.listings_sampled == 0
    assert report.est_monthly_revenue_usd is None
    assert report.most_used_tags == []


@pytest.mark.asyncio
async def test_aggregates_tags_and_revenue() -> None:
    listings = [
        _listing("1", price=20.0, eds=2.0, tags=["mom", "gift"]),
        _listing("2", price=15.0, eds=3.0, tags=["mom", "vintage"]),
        _listing("3", price=25.0, eds=1.0, tags=["vintage"]),
    ]
    svc = ShopAuditService(
        adapters=[_FakeAdapter(Marketplace.ETSY, profile=_profile(), listings=listings)],
    )
    report = await svc.audit(Marketplace.ETSY, "ShopA")

    assert report.listings_sampled == 3
    # Monthly revenue = sum(eds * price) * 30
    # = (2*20 + 3*15 + 1*25) * 30 = 110 * 30 = 3300
    assert report.est_monthly_revenue_usd == 3300.0
    tag_map = dict(report.most_used_tags)
    assert tag_map["mom"] == 2
    assert tag_map["vintage"] == 2
    assert tag_map["gift"] == 1


@pytest.mark.asyncio
async def test_top_listings_sorted_by_monthly_revenue() -> None:
    listings = [
        _listing("low", price=10.0, eds=0.5),     # 5/day, $150/mo
        _listing("hi", price=30.0, eds=5.0),      # 150/day, $4500/mo
        _listing("mid", price=20.0, eds=2.0),     # 40/day, $1200/mo
    ]
    svc = ShopAuditService(
        adapters=[_FakeAdapter(Marketplace.ETSY, profile=_profile(), listings=listings)],
    )
    report = await svc.audit(Marketplace.ETSY, "ShopA")
    assert [l.external_id for l in report.top_listings[:3]] == ["hi", "mid", "low"]


@pytest.mark.asyncio
async def test_unsupported_marketplace_returns_error() -> None:
    svc = ShopAuditService(adapters=[])
    report = await svc.audit(Marketplace.AMAZON_MERCH, "X")
    assert report.error and "unsupported_marketplace" in report.error
    assert report.listings_sampled == 0


@pytest.mark.asyncio
async def test_adapter_error_propagates() -> None:
    svc = ShopAuditService(
        adapters=[_FakeAdapter(Marketplace.ETSY, error="http_403")],
    )
    report = await svc.audit(Marketplace.ETSY, "X")
    assert report.error == "http_403"


@pytest.mark.asyncio
async def test_new_listings_window() -> None:
    listings = [
        _listing("recent1", days_old=5),
        _listing("recent2", days_old=15),
        _listing("old1", days_old=120),
    ]
    svc = ShopAuditService(
        adapters=[_FakeAdapter(Marketplace.ETSY, profile=_profile(), listings=listings)],
    )
    report = await svc.audit(Marketplace.ETSY, "ShopA")
    assert report.new_listings_last_30d == 2
