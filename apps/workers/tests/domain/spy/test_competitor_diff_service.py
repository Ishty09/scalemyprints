"""Competitor diff — pure analysis between two ShopAuditReport snapshots."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from scalemyprints.domain.spy.competitor_diff_service import compute_diff
from scalemyprints.domain.spy.enums import (
    ListingStatus,
    Marketplace,
    ShopAuditDepth,
    VelocityClass,
)
from scalemyprints.domain.spy.models import Listing, ShopAuditReport, ShopProfile


def _profile() -> ShopProfile:
    now = datetime.now(UTC)
    return ShopProfile(
        marketplace=Marketplace.ETSY,
        external_id="ShopX",
        handle="ShopX",
        url="https://etsy.com/shop/ShopX",  # type: ignore[arg-type]
        first_seen_at=now,
        last_seen_at=now,
    )


def _listing(
    eid: str,
    *,
    price: float = 19.99,
    reviews: int | None = 0,
    velocity: VelocityClass = VelocityClass.STEADY,
) -> Listing:
    now = datetime.now(UTC)
    return Listing(
        marketplace=Marketplace.ETSY,
        external_id=eid,
        url=f"https://etsy.com/listing/{eid}",  # type: ignore[arg-type]
        title=f"t {eid}",
        price_usd=price,
        currency="USD",
        reviews_count=reviews,
        velocity_class=velocity,
        status=ListingStatus.ACTIVE,
        first_seen_at=now,
        last_seen_at=now,
    )


def _audit(listings: list[Listing], captured_at: datetime) -> ShopAuditReport:
    return ShopAuditReport(
        shop=_profile(),
        depth=ShopAuditDepth.STANDARD,
        listings_sampled=len(listings),
        top_listings=listings,
        captured_at=captured_at,
    )


def test_detects_new_and_removed_listings() -> None:
    t1 = datetime.now(UTC)
    t2 = t1 + timedelta(days=1)
    prev = _audit([_listing("A"), _listing("B")], t1)
    curr = _audit([_listing("B"), _listing("C")], t2)

    diff = compute_diff(previous=prev, current=curr)
    assert diff.new_listings == ["C"]
    assert diff.removed_listings == ["A"]


def test_detects_price_change() -> None:
    t1 = datetime.now(UTC)
    t2 = t1 + timedelta(days=1)
    prev = _audit([_listing("X", price=10.00)], t1)
    curr = _audit([_listing("X", price=14.50)], t2)

    diff = compute_diff(previous=prev, current=curr)
    assert len(diff.price_changes) == 1
    pc = diff.price_changes[0]
    assert pc["external_id"] == "X"
    assert pc["delta_usd"] == 4.5


def test_detects_restock_signal() -> None:
    t1 = datetime.now(UTC)
    t2 = t1 + timedelta(days=1)
    prev = _audit([_listing("R", reviews=5)], t1)
    curr = _audit([_listing("R", reviews=20)], t2)

    diff = compute_diff(previous=prev, current=curr)
    assert "R" in diff.restock_signals


def test_detects_velocity_mover() -> None:
    t1 = datetime.now(UTC)
    t2 = t1 + timedelta(days=1)
    prev = _audit([_listing("V", velocity=VelocityClass.STEADY)], t1)
    curr = _audit([_listing("V", velocity=VelocityClass.SPIKING)], t2)

    diff = compute_diff(previous=prev, current=curr)
    assert "V" in diff.velocity_movers


def test_no_changes_returns_empty() -> None:
    t1 = datetime.now(UTC)
    audit = _audit([_listing("X"), _listing("Y")], t1)
    diff = compute_diff(previous=audit, current=audit)
    assert diff.new_listings == []
    assert diff.removed_listings == []
    assert diff.price_changes == []
    assert diff.note == "no change"
