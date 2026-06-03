"""
Shop teardown — forensic analysis of a competitor's shop.

Given (marketplace, shop handle), produce a ShopAuditReport with:
- Profile fields (display name, sales, location)
- Top N listings ranked by est. monthly revenue
- Most-used tags + frequency
- Average price + range
- New listings in the last 30 days
- Inter-arrival cadence between new listings (median days)
- Est. monthly revenue across sampled listings

Depth (SHALLOW / STANDARD / DEEP) controls how many listings the adapter
returns; the analysis logic is the same.

We never raise — failures land in `error` on the report.
"""

from __future__ import annotations

import itertools
import statistics
import time
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.spy.enums import (
    Marketplace,
    ShopAuditDepth,
)
from scalemyprints.domain.spy.models import (
    Listing,
    ShopAuditReport,
    ShopProfile,
)

if TYPE_CHECKING:
    from scalemyprints.domain.spy.ports import SpyMarketplaceAdapter

logger = get_logger(__name__)

DEFAULT_TOP_N = 10
DEFAULT_TAG_TOP_N = 20


class ShopAuditService:
    """Orchestrates a shop teardown across one marketplace."""

    def __init__(
        self,
        *,
        adapters: list[SpyMarketplaceAdapter],
    ) -> None:
        self._by_marketplace = {a.marketplace: a for a in adapters}

    async def audit(
        self,
        marketplace: Marketplace,
        handle_or_id: str,
        *,
        depth: ShopAuditDepth = ShopAuditDepth.STANDARD,
    ) -> ShopAuditReport:
        time.monotonic()
        log = logger.bind(marketplace=marketplace.value, handle=handle_or_id, depth=depth.value)

        adapter = self._by_marketplace.get(marketplace)
        if adapter is None:
            log.warning("shop_audit_unsupported_marketplace")
            return _empty_report(
                marketplace=marketplace,
                handle=handle_or_id,
                depth=depth,
                error=f"unsupported_marketplace: {marketplace.value}",
            )

        result = await adapter.fetch_shop(handle_or_id, depth=depth)
        if result.error or result.profile is None:
            log.info("shop_audit_fetch_failed", error=result.error)
            return _empty_report(
                marketplace=marketplace,
                handle=handle_or_id,
                depth=depth,
                error=result.error or "no_profile_returned",
            )

        listings = result.listings
        analysis = _analyze(listings, top_n=DEFAULT_TOP_N, tag_top_n=DEFAULT_TAG_TOP_N)

        log.info(
            "shop_audit_complete",
            listings_sampled=len(listings),
            est_monthly_revenue_usd=analysis["est_monthly_revenue_usd"],
        )

        return ShopAuditReport(
            shop=result.profile,
            depth=depth,
            listings_sampled=len(listings),
            est_monthly_revenue_usd=analysis["est_monthly_revenue_usd"],
            top_listings=analysis["top_listings"],
            most_used_tags=analysis["most_used_tags"],
            avg_price_usd=analysis["avg_price_usd"],
            new_listings_last_30d=analysis["new_listings_last_30d"],
            restock_cadence_days=analysis["restock_cadence_days"],
            captured_at=datetime.now(UTC),
        )


# -----------------------------------------------------------------------------
# Pure analysis — no I/O, no state
# -----------------------------------------------------------------------------


def _analyze(
    listings: list[Listing],
    *,
    top_n: int = DEFAULT_TOP_N,
    tag_top_n: int = DEFAULT_TAG_TOP_N,
) -> dict[str, object]:
    if not listings:
        return {
            "est_monthly_revenue_usd": None,
            "top_listings": [],
            "most_used_tags": [],
            "avg_price_usd": None,
            "new_listings_last_30d": 0,
            "restock_cadence_days": None,
        }

    # Revenue
    def _monthly_for(listing: Listing) -> float:
        eds = listing.est_daily_sales or 0.0
        p = listing.price_usd or 0.0
        return eds * p * 30.0

    monthly = [_monthly_for(l) for l in listings]
    total_monthly = sum(monthly) or None

    # Top by revenue (fall back to favorites if no sales estimate)
    ranked = sorted(
        listings,
        key=lambda l: (
            (l.est_daily_sales or 0.0) * (l.price_usd or 0.0),
            l.favorites or 0,
        ),
        reverse=True,
    )
    top_listings = ranked[:top_n]

    # Tags — case-insensitive count
    tag_counter: Counter[str] = Counter()
    for l in listings:
        for t in l.tags:
            tag = (t or "").strip().lower()
            if tag:
                tag_counter[tag] += 1
    most_used_tags = [(tag, count) for tag, count in tag_counter.most_common(tag_top_n)]

    # Avg price
    prices = [l.price_usd for l in listings if l.price_usd is not None]
    avg_price = round(statistics.fmean(prices), 2) if prices else None

    # New listings + restock cadence (uses first_seen_at)
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=30)
    new_last_30 = sum(1 for l in listings if l.first_seen_at >= cutoff)

    first_seen_sorted = sorted(l.first_seen_at for l in listings)
    if len(first_seen_sorted) >= 2:
        # strict=False because pairs(a, b) is naturally n-1 from n elements
        deltas_days = [
            (b - a).total_seconds() / 86400.0
            for a, b in itertools.pairwise(first_seen_sorted)
            if (b - a).total_seconds() > 0
        ]
        cadence = round(statistics.median(deltas_days), 2) if deltas_days else None
    else:
        cadence = None

    return {
        "est_monthly_revenue_usd": round(total_monthly, 2) if total_monthly is not None else None,
        "top_listings": top_listings,
        "most_used_tags": most_used_tags,
        "avg_price_usd": avg_price,
        "new_listings_last_30d": new_last_30,
        "restock_cadence_days": cadence,
    }


def _empty_report(
    *,
    marketplace: Marketplace,
    handle: str,
    depth: ShopAuditDepth,
    error: str,
) -> ShopAuditReport:
    now = datetime.now(UTC)
    return ShopAuditReport(
        shop=ShopProfile(
            marketplace=marketplace,
            external_id=handle,
            handle=handle,
            url=f"https://example.invalid/{marketplace.value}/{handle}",  # type: ignore[arg-type]
            first_seen_at=now,
            last_seen_at=now,
        ),
        depth=depth,
        listings_sampled=0,
        captured_at=now,
        error=error,
    )
