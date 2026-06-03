"""Saturation/Difficulty scoring."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from scalemyprints.domain.spy import saturation_service
from scalemyprints.domain.spy.enums import (
    ListingStatus,
    Marketplace,
    SaturationClass,
    VelocityClass,
)
from scalemyprints.domain.spy.models import Listing


def _l(
    eid: str,
    *,
    shop: str,
    price: float = 20.0,
    eds: float = 1.0,
    velocity: VelocityClass = VelocityClass.STEADY,
    days_old: int = 90,
) -> Listing:
    now = datetime.now(UTC)
    return Listing(
        marketplace=Marketplace.ETSY,
        external_id=eid,
        url=f"https://etsy.com/listing/{eid}",  # type: ignore[arg-type]
        title=f"d {eid}",
        price_usd=price,
        currency="USD",
        shop_handle=shop,
        est_daily_sales=eds,
        velocity_class=velocity,
        status=ListingStatus.ACTIVE,
        first_seen_at=now - timedelta(days=days_old),
        last_seen_at=now,
    )


def test_empty_input_returns_open() -> None:
    score = saturation_service.compute([])
    assert score.score == 0
    assert score.saturation_class == SaturationClass.OPEN
    assert "no listings" in score.explanation.lower()


def test_few_concentrated_listings_score_low() -> None:
    # 5 listings all from same shop → low density, high concentration
    # (HHI=1.0), no velocity, recent
    listings = [_l(str(i), shop="ShopX", days_old=10) for i in range(5)]
    score = saturation_service.compute(listings, phrase="weird niche")
    assert score.saturation_class in (SaturationClass.OPEN, SaturationClass.MILD)
    assert score.unique_shops == 1
    assert score.hhi == 1.0
    assert score.concentration_component == 0  # HHI=1 → 0 pts


def test_many_diffuse_listings_score_high() -> None:
    # 100 listings, 50 different shops, half spiking, old listings
    listings = []
    for i in range(100):
        shop = f"Shop{i % 50}"
        velocity = (
            VelocityClass.SPIKING if i % 2 == 0 else VelocityClass.STEADY
        )
        listings.append(_l(str(i), shop=shop, velocity=velocity, days_old=300))
    score = saturation_service.compute(listings, phrase="popular niche")
    assert score.saturation_class in (
        SaturationClass.CROWDED,
        SaturationClass.SATURATED,
    )
    assert score.unique_shops == 50
    # Density should be near maxed
    assert score.density_component >= 20


def test_phrase_is_quoted_in_explanation() -> None:
    listings = [_l("1", shop="ShopA")]
    score = saturation_service.compute(listings, phrase="my keyword")
    assert '"my keyword"' in score.explanation


def test_score_bounds() -> None:
    listings = [
        _l(str(i), shop=f"S{i}", velocity=VelocityClass.SPIKING, days_old=730)
        for i in range(2000)
    ]
    score = saturation_service.compute(listings)
    assert 0 <= score.score <= 100
