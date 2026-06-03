"""
Spy search orchestrator — fan out to every selected marketplace and
fuse the results.

Strategy:
- Caller provides a SpyQuery with optional `marketplaces` filter
- We dispatch in parallel (asyncio.gather) to every selected adapter
- Each adapter returns a MarketplaceSearchResult; we merge the
  successful listings, record failures by source, and persist any
  newly-seen listings to the ListingStore for velocity tracking
- We DO NOT raise on adapter failure — the response carries
  `sources_used` / `sources_failed` so the UI can surface partial state

No business logic about ranking is in here — that lives downstream in
the velocity & saturation services.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.spy.models import (
    Listing,
    SpyQuery,
    SpySearchResult,
)

if TYPE_CHECKING:
    from scalemyprints.domain.spy.enums import Marketplace
    from scalemyprints.domain.spy.ports import (
        ListingStore,
        SpyMarketplaceAdapter,
    )

logger = get_logger(__name__)


class SpySearchService:
    """Coordinates multi-marketplace text/URL search."""

    def __init__(
        self,
        *,
        adapters: list[SpyMarketplaceAdapter],
        listing_store: ListingStore | None = None,
    ) -> None:
        self._adapters = adapters
        self._adapters_by_mkt = {a.marketplace: a for a in adapters}
        self._store = listing_store

    async def run(self, query: SpyQuery) -> SpySearchResult:
        start = time.monotonic()
        targets = self._select_adapters(query)
        log = logger.bind(
            marketplaces=[m.value for m in (a.marketplace for a in targets)],
            text=query.text,
            url=str(query.listing_url) if query.listing_url else None,
        )
        if not targets:
            log.info("spy_search_no_adapters_available")
            return SpySearchResult(
                query=query,
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        log.info("spy_search_dispatch")

        results = await asyncio.gather(
            *(adapter.search(query, limit=query.limit) for adapter in targets),
            return_exceptions=True,
        )

        merged: list[Listing] = []
        used: list[Marketplace] = []
        failed: list[tuple[Marketplace, str]] = []

        for adapter, raw in zip(targets, results, strict=True):
            if isinstance(raw, BaseException):
                # Adapter raised — contract violation, but we tolerate it
                logger.warning(
                    "spy_adapter_raised",
                    marketplace=adapter.marketplace.value,
                    error=str(raw),
                )
                failed.append((adapter.marketplace, f"raised: {type(raw).__name__}"))
                continue

            if raw.error or not raw.listings:
                if raw.error:
                    failed.append((adapter.marketplace, raw.error))
                else:
                    used.append(adapter.marketplace)
                continue

            used.append(adapter.marketplace)
            merged.extend(raw.listings)

        # Optional persistence — don't let a store failure break the search response
        if self._store is not None and merged:
            await self._persist_silently(merged)

        return SpySearchResult(
            query=query,
            listings=merged,
            sources_used=used,
            sources_failed=failed,
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _select_adapters(self, query: SpyQuery) -> list[SpyMarketplaceAdapter]:
        if not query.marketplaces:
            return list(self._adapters)
        return [a for a in self._adapters if a.marketplace in query.marketplaces]

    async def _persist_silently(self, listings: list[Listing]) -> None:
        """Best-effort write to the listing store; never raise."""
        if self._store is None:
            return
        for listing in listings:
            try:
                await self._store.upsert_listing(listing)
            except Exception as e:  # store failure must not break search
                logger.warning(
                    "spy_listing_persist_failed",
                    marketplace=listing.marketplace.value,
                    external_id=listing.external_id,
                    error=str(e),
                )
