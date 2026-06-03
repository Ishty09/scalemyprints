"""
Saturation / Difficulty score (0–100).

A single number that tells a seller "how crowded is this niche / design?"

Inputs (any subset; we degrade gracefully):
- phrase / keyword (string)
- candidate listings (already pulled by SpySearchService) — list[Listing]
- est. GMV pool — sum of (est_daily_sales × price) across candidates

Algorithm (0 = wide open, 100 = saturated):
1. Density component (40 pts): number of candidate listings,
   log-scaled so 50 listings ≈ 30 pts, 500 ≈ 38, 5000 ≈ ~40
2. Concentration component (30 pts): Herfindahl-Hirschman index of
   shop GMV share. Highly concentrated = easier to enter (one giant
   plus many small) → lower saturation. Diffuse = many viable
   competitors → higher.
3. Velocity component (15 pts): proportion of candidates in
   {SPIKING, EXPLOSIVE}. If most are still spiking, late entry is risky.
4. Recency component (15 pts): median age of top listings. Older
   listings → entrenched competition → higher saturation.

Output: SaturationScore with raw components for debuggability.

This is intentionally NOT an ML model. The transparency matters for a
B2B tool — sellers want to *understand* why a niche scored 87/100.
"""

from __future__ import annotations

import math
import statistics
from datetime import UTC, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.spy.enums import (
    SaturationClass,
    VelocityClass,
)
from scalemyprints.domain.spy.models import Listing  # noqa: TC001

logger = get_logger(__name__)


Score = Annotated[int, Field(ge=0, le=100)]


class SaturationScore(BaseModel):
    """Breakdown of the 0–100 score so the UI can show *why*."""

    model_config = ConfigDict(frozen=True)

    score: Score
    saturation_class: SaturationClass
    listings_count: int = Field(ge=0)
    unique_shops: int = Field(ge=0)
    hhi: float = Field(ge=0.0, le=1.0)                 # Herfindahl–Hirschman index
    gmv_pool_usd: float = Field(ge=0.0)
    density_component: Score
    concentration_component: Score
    velocity_component: Score
    recency_component: Score
    explanation: str


def compute(listings: list[Listing], *, phrase: str | None = None) -> SaturationScore:
    """Compute saturation from a list of candidate listings."""
    if not listings:
        return SaturationScore(
            score=0,
            saturation_class=SaturationClass.OPEN,
            listings_count=0,
            unique_shops=0,
            hhi=0.0,
            gmv_pool_usd=0.0,
            density_component=0,
            concentration_component=0,
            velocity_component=0,
            recency_component=0,
            explanation=_explain(phrase, 0, "no listings sampled — wide open"),
        )

    # ---- Density (40 pts) ------------------------------------------------
    # Log curve: 50 → 30, 500 → 38, 5000 → 40
    n = len(listings)
    density = min(40, round(40.0 * math.log10(max(n, 1)) / math.log10(5000.0)))

    # ---- Concentration (30 pts) -----------------------------------------
    # HHI computed on shop-level GMV share. A market with one player has
    # HHI=1 (easy to enter — niche dominated by one), a perfectly diffuse
    # market has HHI ~ 1/n_shops. Map low HHI → higher saturation.
    shop_gmv: dict[str, float] = {}
    for l in listings:
        shop_key = l.shop_handle or l.shop_external_id or f"_anon_{l.external_id}"
        gmv = (l.est_daily_sales or 0.0) * (l.price_usd or 0.0) * 30.0
        shop_gmv[shop_key] = shop_gmv.get(shop_key, 0.0) + gmv

    total_gmv = sum(shop_gmv.values()) or None
    if total_gmv:
        shares = [g / total_gmv for g in shop_gmv.values()]
        hhi = sum(s * s for s in shares)
    else:
        # No GMV data — fall back to equal-weight by listing count
        listings_per_shop: dict[str, int] = {}
        for l in listings:
            shop_key = l.shop_handle or l.shop_external_id or f"_anon_{l.external_id}"
            listings_per_shop[shop_key] = listings_per_shop.get(shop_key, 0) + 1
        total_l = sum(listings_per_shop.values())
        shares = [c / total_l for c in listings_per_shop.values()]
        hhi = sum(s * s for s in shares)

    # Lower HHI → more diffuse competition → higher saturation
    concentration = round(30.0 * (1.0 - hhi))
    concentration = max(0, min(30, concentration))

    # ---- Velocity (15 pts) -----------------------------------------------
    hot = sum(
        1
        for l in listings
        if l.velocity_class in (VelocityClass.SPIKING, VelocityClass.EXPLOSIVE)
    )
    rising_share = hot / n
    velocity_pts = round(15.0 * rising_share)

    # ---- Recency (15 pts) -----------------------------------------------
    # Median age in days; older = entrenched = higher saturation
    now = datetime.now(UTC)
    ages = [(now - l.first_seen_at).total_seconds() / 86400.0 for l in listings]
    median_age = statistics.median(ages) if ages else 0.0
    # 30 days → 0 pts, 365+ days → 15 pts (linear)
    recency_pts = max(0, min(15, round(15.0 * min(median_age, 365.0) / 365.0)))

    score = density + concentration + velocity_pts + recency_pts
    score = max(0, min(100, score))

    klass = _classify(score)

    return SaturationScore(
        score=score,
        saturation_class=klass,
        listings_count=n,
        unique_shops=len(shop_gmv),
        hhi=round(hhi, 4),
        gmv_pool_usd=round(total_gmv or 0.0, 2),
        density_component=density,
        concentration_component=concentration,
        velocity_component=velocity_pts,
        recency_component=recency_pts,
        explanation=_explain(phrase, score, _build_summary(n, hhi, rising_share, median_age, klass)),
    )


def _classify(score: int) -> SaturationClass:
    if score >= 75:
        return SaturationClass.SATURATED
    if score >= 50:
        return SaturationClass.CROWDED
    if score >= 25:
        return SaturationClass.MILD
    return SaturationClass.OPEN


def _build_summary(
    listings: int,
    hhi: float,
    rising_share: float,
    median_age_days: float,
    klass: SaturationClass,
) -> str:
    parts = [
        f"{listings} listings sampled",
        f"HHI={hhi:.2f}",
        f"{round(rising_share * 100)}% spiking",
        f"median age {median_age_days:.0f}d",
    ]
    return f"{klass.value.upper()} — " + ", ".join(parts)


def _explain(phrase: str | None, score: int, body: str) -> str:
    head = f"saturation={score}/100"
    if phrase:
        head = f'"{phrase}" {head}'
    return f"{head}: {body}"
