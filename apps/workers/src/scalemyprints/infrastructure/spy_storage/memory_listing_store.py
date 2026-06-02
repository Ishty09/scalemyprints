"""
In-memory ListingStore. Resets on process restart — fine for tests
and local dev when Supabase isn't configured.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import TYPE_CHECKING

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.spy.ports import ListingStore

if TYPE_CHECKING:
    from scalemyprints.domain.spy.enums import Marketplace
    from scalemyprints.domain.spy.models import Listing, ListingSnapshot

logger = get_logger(__name__)


class MemoryListingStore(ListingStore):
    """Process-local ListingStore implementation."""

    def __init__(self) -> None:
        self._listings: dict[str, Listing] = {}
        self._by_external: dict[tuple[str, str], str] = {}
        self._snapshots: dict[str, list[ListingSnapshot]] = defaultdict(list)

    async def upsert_listing(self, listing: Listing) -> str:
        key = (listing.marketplace.value, listing.external_id)
        existing = self._by_external.get(key)
        if existing:
            # Replace stored listing but keep id stable
            self._listings[existing] = listing
            return existing
        new_id = str(uuid.uuid4())
        self._by_external[key] = new_id
        self._listings[new_id] = listing
        return new_id

    async def record_snapshot(self, snapshot: ListingSnapshot) -> None:
        self._snapshots[snapshot.listing_id].append(snapshot)

    async def get_listing(self, listing_id: str) -> Listing | None:
        return self._listings.get(listing_id)

    async def get_by_external(
        self,
        marketplace: Marketplace,
        external_id: str,
    ) -> tuple[str, Listing] | None:
        key = (marketplace.value, external_id)
        listing_id = self._by_external.get(key)
        if not listing_id:
            return None
        listing = self._listings.get(listing_id)
        if listing is None:
            return None
        return listing_id, listing

    async def recent_snapshots(
        self,
        listing_id: str,
        *,
        days: int = 14,
        limit: int = 200,
    ) -> list[ListingSnapshot]:
        rows = self._snapshots.get(listing_id, [])
        # Newest first, capped
        ordered = sorted(rows, key=lambda s: s.captured_at, reverse=True)
        return ordered[:limit]

    # Test helpers ---------------------------------------------------------

    def clear(self) -> None:
        self._listings.clear()
        self._by_external.clear()
        self._snapshots.clear()

    def size(self) -> int:
        return len(self._listings)
