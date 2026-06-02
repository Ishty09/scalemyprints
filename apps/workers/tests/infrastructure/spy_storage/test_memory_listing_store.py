"""Tests for the in-memory listing store."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from scalemyprints.domain.spy.enums import (
    ListingStatus,
    Marketplace,
    VelocityClass,
)
from scalemyprints.domain.spy.models import Listing, ListingSnapshot
from scalemyprints.infrastructure.spy_storage.memory_listing_store import (
    MemoryListingStore,
)


def _listing(external_id: str = "X1") -> Listing:
    now = datetime.now(UTC)
    return Listing(
        marketplace=Marketplace.ETSY,
        external_id=external_id,
        url=f"https://example.com/{external_id}",  # type: ignore[arg-type]
        title="hello",
        status=ListingStatus.ACTIVE,
        velocity_class=VelocityClass.STEADY,
        first_seen_at=now,
        last_seen_at=now,
    )


@pytest.mark.asyncio
async def test_upsert_assigns_stable_id() -> None:
    store = MemoryListingStore()
    listing = _listing()
    first = await store.upsert_listing(listing)
    second = await store.upsert_listing(listing)
    assert first == second


@pytest.mark.asyncio
async def test_get_listing_round_trip() -> None:
    store = MemoryListingStore()
    listing = _listing()
    listing_id = await store.upsert_listing(listing)
    back = await store.get_listing(listing_id)
    assert back is not None
    assert back.external_id == "X1"


@pytest.mark.asyncio
async def test_recent_snapshots_orders_newest_first() -> None:
    store = MemoryListingStore()
    listing_id = await store.upsert_listing(_listing())

    base = datetime.now(UTC)
    for i in range(5):
        await store.record_snapshot(
            ListingSnapshot(
                listing_id=listing_id,
                captured_at=base - timedelta(hours=i),
                est_daily_sales=float(i),
            )
        )
    series = await store.recent_snapshots(listing_id, limit=5)
    assert len(series) == 5
    # Newest should be the one with smallest hour offset (i=0)
    assert series[0].est_daily_sales == 0.0
    assert series[-1].est_daily_sales == 4.0


@pytest.mark.asyncio
async def test_get_by_external() -> None:
    store = MemoryListingStore()
    listing = _listing("E42")
    listing_id = await store.upsert_listing(listing)

    out = await store.get_by_external(Marketplace.ETSY, "E42")
    assert out is not None
    assert out[0] == listing_id
    assert out[1].external_id == "E42"

    missing = await store.get_by_external(Marketplace.ETSY, "nope")
    assert missing is None
