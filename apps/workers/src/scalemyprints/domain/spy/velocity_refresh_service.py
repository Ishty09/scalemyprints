"""
Velocity refresh orchestrator.

Picks up to N tracked listings, re-fetches each from its marketplace
adapter, records a fresh ListingSnapshot, and re-classifies the
listing's velocity_class via VelocityAnalyzer.

Designed to be called by:
- A cron worker (Cloudflare Workers cron / Vercel cron / GitHub Actions)
- A FastAPI internal endpoint with an internal-secret header
- A manual CLI invocation for ops debugging

We process in bounded batches with a per-batch concurrency cap so a
single run can't trigger a thundering herd against any one
marketplace. Adapter failures are logged and skipped, never raised.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.spy.enums import Marketplace, VelocityClass
from scalemyprints.domain.spy.models import (  # noqa: TC001 — runtime use for pydantic fields
    Listing,
    ListingSnapshot,
    VelocitySignal,
)

if TYPE_CHECKING:
    from scalemyprints.domain.spy.ports import (
        ListingStore,
        SpyMarketplaceAdapter,
        VelocityAnalyzer,
    )

logger = get_logger(__name__)


class VelocityRefreshSummary(BaseModel):
    """Result envelope from a refresh run."""

    model_config = ConfigDict(frozen=True)

    started_at: datetime
    completed_at: datetime
    duration_ms: int = Field(ge=0)
    candidates: int = Field(ge=0)
    refreshed: int = Field(ge=0)
    failed: int = Field(ge=0)
    spikes_detected: int = Field(ge=0)
    by_marketplace: dict[str, int] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    # Phase 4.5 — surfaced for WatchlistService.evaluate()
    velocity_signals: list[VelocitySignal] = Field(default_factory=list)


class VelocityRefreshService:
    """Coordinates re-fetch → snapshot → re-classify across a batch."""

    def __init__(
        self,
        *,
        adapters: list[SpyMarketplaceAdapter],
        listing_store: ListingStore,
        analyzer: VelocityAnalyzer,
        batch_concurrency: int = 4,
    ) -> None:
        self._by_marketplace = {a.marketplace: a for a in adapters}
        self._store = listing_store
        self._analyzer = analyzer
        self._concurrency = batch_concurrency

    async def refresh(
        self,
        candidates: list[tuple[str, Listing]],
    ) -> VelocityRefreshSummary:
        """
        Refresh a batch of (listing_id, Listing) pairs.

        Caller picks the candidates — typically the N oldest by
        `last_seen_at`. We update each via its adapter and persist a
        snapshot. Returns a summary including spike count.
        """
        started = datetime.now(UTC)
        start_mono = time.monotonic()

        sem = asyncio.Semaphore(self._concurrency)
        results: list[_RefreshOutcome] = []

        async def _one(listing_id: str, listing: Listing) -> _RefreshOutcome:
            async with sem:
                return await self._refresh_one(listing_id, listing)

        if candidates:
            results = await asyncio.gather(
                *(_one(lid, l) for lid, l in candidates),
            )

        completed = datetime.now(UTC)
        refreshed = sum(1 for r in results if r.refreshed)
        failed = sum(1 for r in results if not r.refreshed)
        spikes = sum(1 for r in results if r.spike_detected)

        by_mkt: dict[str, int] = {}
        for r in results:
            if r.refreshed:
                by_mkt[r.marketplace.value] = by_mkt.get(r.marketplace.value, 0) + 1

        errors = [r.error for r in results if r.error][:20]
        velocity_signals = [r.signal for r in results if r.signal is not None]

        summary = VelocityRefreshSummary(
            started_at=started,
            completed_at=completed,
            duration_ms=int((time.monotonic() - start_mono) * 1000),
            candidates=len(candidates),
            refreshed=refreshed,
            failed=failed,
            spikes_detected=spikes,
            by_marketplace=by_mkt,
            errors=errors,
            velocity_signals=velocity_signals,
        )
        logger.info(
            "velocity_refresh_completed",
            **summary.model_dump(exclude={"errors"}),
        )
        return summary

    # ---------------------- internals -------------------------------------

    async def _refresh_one(
        self,
        listing_id: str,
        listing: Listing,
    ) -> _RefreshOutcome:
        adapter = self._by_marketplace.get(listing.marketplace)
        if adapter is None:
            return _RefreshOutcome(
                marketplace=listing.marketplace,
                refreshed=False,
                error=f"no_adapter_for_{listing.marketplace.value}",
            )

        detail = await adapter.fetch_listing(listing.external_id)
        if detail.error or detail.listing is None:
            return _RefreshOutcome(
                marketplace=listing.marketplace,
                refreshed=False,
                error=detail.error or "no_listing_returned",
            )

        fresh = detail.listing
        snapshot = ListingSnapshot(
            listing_id=listing_id,
            captured_at=datetime.now(UTC),
            price_usd=fresh.price_usd,
            favorites=fresh.favorites,
            reviews_count=fresh.reviews_count,
            rating=fresh.rating,
            est_daily_sales=_derive_eds(listing, fresh),
        )
        try:
            await self._store.record_snapshot(snapshot)
        except Exception as e:
            return _RefreshOutcome(
                marketplace=listing.marketplace,
                refreshed=False,
                error=f"snapshot_persist_failed: {e}",
            )

        # Re-upsert listing so last_seen_at + favorites/reviews refresh
        try:
            await self._store.upsert_listing(fresh)
        except Exception as e:
            logger.warning("velocity_refresh_upsert_failed", error=str(e))

        # Re-classify using the last N snapshots
        try:
            series = await self._store.recent_snapshots(listing_id, days=14, limit=200)
        except Exception as e:
            logger.warning("velocity_refresh_series_load_failed", error=str(e))
            series = []

        signal = await self._analyzer.analyze(listing_id, series)
        spike = signal is not None and signal.velocity_class in (
            VelocityClass.SPIKING,
            VelocityClass.EXPLOSIVE,
        )

        return _RefreshOutcome(
            marketplace=listing.marketplace,
            refreshed=True,
            spike_detected=spike,
            signal=signal if spike else None,
        )


class _RefreshOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    marketplace: Marketplace
    signal: VelocitySignal | None = None
    refreshed: bool
    spike_detected: bool = False
    error: str | None = None


def _derive_eds(prev: Listing, fresh: Listing) -> float | None:
    """
    Quick-and-dirty est-daily-sales derivation when the adapter doesn't
    provide one directly.

    Uses delta in `reviews_count` × 30 (Etsy review-rate is ~3% so this
    over-estimates by 30×, but it's directionally correct for spike
    detection which is z-score-based).

    Phase 3 swaps this for a proper per-marketplace estimator.
    """
    if fresh.est_daily_sales is not None:
        return fresh.est_daily_sales
    if prev.reviews_count is None or fresh.reviews_count is None:
        return None
    delta = max(0, fresh.reviews_count - prev.reviews_count)
    elapsed_days = max(1.0, (fresh.last_seen_at - prev.last_seen_at).total_seconds() / 86400.0)
    return round((delta / elapsed_days) * 30.0, 3)
