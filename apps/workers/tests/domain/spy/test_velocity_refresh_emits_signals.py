"""Phase 4.5 — velocity refresh surfaces spike signals so the watchlist
engine can evaluate against them."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from scalemyprints.domain.spy.enums import (
    ListingStatus,
    Marketplace,
    ShopAuditDepth,
    VelocityClass,
)
from scalemyprints.domain.spy.models import Listing, ListingSnapshot
from scalemyprints.domain.spy.ports import (
    ListingDetailResult,
    MarketplaceSearchResult,
    ShopFetchResult,
    SpyMarketplaceAdapter,
)
from scalemyprints.domain.spy.velocity_refresh_service import VelocityRefreshService
from scalemyprints.domain.spy.velocity_service import VelocityAnalyzer
from scalemyprints.domain.spy.watchlist_models import (
    AlertChannelConfig,
    AlertChannel,
    AlertTrigger,
    WatchType,
)
from scalemyprints.domain.spy.watchlist_service import WatchlistService
from scalemyprints.infrastructure.alert_dispatchers.in_app import InAppAlertDispatcher
from scalemyprints.infrastructure.spy_storage.memory_listing_store import (
    MemoryListingStore,
)
from scalemyprints.infrastructure.spy_storage.memory_watchlist_store import (
    MemoryAlertStore,
    MemoryWatchlistStore,
)


class _FakeAdapter(SpyMarketplaceAdapter):
    """Returns a 'fresher' listing whose review count jumped → spike."""

    def __init__(self, fresh: Listing) -> None:
        self._fresh = fresh

    @property
    def marketplace(self) -> Marketplace:
        return Marketplace.ETSY

    async def search(self, query, *, limit=20):
        return MarketplaceSearchResult(marketplace=Marketplace.ETSY)

    async def fetch_listing(self, external_id: str) -> ListingDetailResult:
        return ListingDetailResult(listing=self._fresh)

    async def fetch_shop(self, handle_or_id: str, *, depth=ShopAuditDepth.STANDARD):
        return ShopFetchResult()


@pytest.mark.asyncio
async def test_refresh_surfaces_spike_signal_and_fires_watchlist_alert() -> None:
    store = MemoryListingStore()
    now = datetime.now(UTC)

    # Seed an old version of the listing
    old = Listing(
        marketplace=Marketplace.ETSY,
        external_id="X1",
        url="https://etsy.com/listing/X1",  # type: ignore[arg-type]
        title="seasonal mug",
        reviews_count=10,
        status=ListingStatus.ACTIVE,
        velocity_class=VelocityClass.STEADY,
        first_seen_at=now - timedelta(days=30),
        last_seen_at=now - timedelta(days=10),
    )
    listing_id = await store.upsert_listing(old)

    # Pre-load 14 days of snapshots showing the baseline
    for i in range(14, 0, -1):
        await store.record_snapshot(
            ListingSnapshot(
                listing_id=listing_id,
                captured_at=now - timedelta(days=i),
                est_daily_sales=2.0,
            )
        )

    # The fresh listing has dramatically more reviews → derive_eds spikes
    fresh = old.model_copy(
        update={"reviews_count": 500, "last_seen_at": now}
    )

    velocity_svc = VelocityRefreshService(
        adapters=[_FakeAdapter(fresh)],
        listing_store=store,
        analyzer=VelocityAnalyzer(),
    )
    summary = await velocity_svc.refresh([(listing_id, old)])
    assert summary.refreshed == 1
    assert summary.spikes_detected == 1
    assert len(summary.velocity_signals) == 1
    spike = summary.velocity_signals[0]
    assert spike.listing_id == listing_id
    assert spike.z_score > 2.5

    # Now wire the watchlist engine and prove the alert fires
    watchlist_store = MemoryWatchlistStore()
    alert_store = MemoryAlertStore()
    watchlist_svc = WatchlistService(
        watchlist_store=watchlist_store,
        alert_store=alert_store,
        dispatchers=[InAppAlertDispatcher()],
    )
    await watchlist_svc.create(
        user_id="user-1",
        watch_type=WatchType.LISTING,
        target=listing_id,
        label=None,
        triggers=[AlertTrigger.VELOCITY_SPIKE],
        channels=[AlertChannelConfig(channel=AlertChannel.IN_APP)],
    )

    result = await watchlist_svc.evaluate(velocity_signals=summary.velocity_signals)
    assert result.alerts_created == 1

    alerts = await alert_store.list_for_user("user-1")
    assert len(alerts) == 1
    assert alerts[0].trigger == AlertTrigger.VELOCITY_SPIKE
