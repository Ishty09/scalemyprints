"""
Competitor diff tracker.

Given two shop audit snapshots for the same (marketplace, handle),
compute the delta:
- new_listings (in current, not in previous)
- removed_listings (in previous, not in current)
- price_changes (per-listing delta)
- restock_signals (listings whose review counts jumped)
- velocity_movers (listings whose velocity_class upgraded)

Pure analysis — no I/O. The caller fetches the audits.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.spy.watchlist_models import CompetitorDiff

if TYPE_CHECKING:
    from scalemyprints.domain.spy.models import Listing, ShopAuditReport

logger = get_logger(__name__)


REVIEW_RESTOCK_THRESHOLD = 10
"""How many new reviews count as a restock signal."""


def compute_diff(
    *,
    previous: ShopAuditReport,
    current: ShopAuditReport,
) -> CompetitorDiff:
    prev_by_id = {l.external_id: l for l in previous.top_listings}
    curr_by_id = {l.external_id: l for l in current.top_listings}

    new_ids = sorted(curr_by_id.keys() - prev_by_id.keys())
    removed_ids = sorted(prev_by_id.keys() - curr_by_id.keys())

    price_changes: list[dict[str, object]] = []
    restock_signals: list[str] = []
    velocity_movers: list[str] = []

    for eid in sorted(curr_by_id.keys() & prev_by_id.keys()):
        prev_l = prev_by_id[eid]
        curr_l = curr_by_id[eid]

        if (
            prev_l.price_usd is not None
            and curr_l.price_usd is not None
            and abs(prev_l.price_usd - curr_l.price_usd) >= 0.50
        ):
            price_changes.append(
                {
                    "external_id": eid,
                    "previous_price_usd": prev_l.price_usd,
                    "current_price_usd": curr_l.price_usd,
                    "delta_usd": round(curr_l.price_usd - prev_l.price_usd, 2),
                }
            )

        if _is_restock(prev_l, curr_l):
            restock_signals.append(eid)

        if curr_l.velocity_class != prev_l.velocity_class:
            velocity_movers.append(eid)

    return CompetitorDiff(
        marketplace=current.shop.marketplace.value,
        handle=current.shop.handle,
        previous_at=previous.captured_at,
        current_at=current.captured_at,
        new_listings=new_ids,
        removed_listings=removed_ids,
        price_changes=price_changes,
        restock_signals=restock_signals,
        velocity_movers=velocity_movers,
        note=_summarize(
            new_ids,
            removed_ids,
            price_changes,
            restock_signals,
            velocity_movers,
        ),
    )


def _is_restock(prev: Listing, curr: Listing) -> bool:
    if prev.reviews_count is None or curr.reviews_count is None:
        return False
    return (curr.reviews_count - prev.reviews_count) >= REVIEW_RESTOCK_THRESHOLD


def _summarize(
    new_ids: list[str],
    removed_ids: list[str],
    price_changes: list[dict[str, object]],
    restocks: list[str],
    velocity_movers: list[str],
) -> str:
    parts: list[str] = []
    if new_ids:
        parts.append(f"{len(new_ids)} new")
    if removed_ids:
        parts.append(f"{len(removed_ids)} removed")
    if price_changes:
        parts.append(f"{len(price_changes)} price changes")
    if restocks:
        parts.append(f"{len(restocks)} restock signals")
    if velocity_movers:
        parts.append(f"{len(velocity_movers)} velocity movers")
    return ", ".join(parts) or "no change"
