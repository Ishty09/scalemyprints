"""
Niche scoring service.

Pure domain logic — converts raw signals (demand, trend, competition,
profitability, seasonality) into a single Niche Health Score (0-100).

No external dependencies. Fully unit-testable in isolation.

Formula:
    NHS = (Demand × 0.35)
        + (Trend × 0.20)
        + ((100 - Competition) × 0.15)
        + (Profitability × 0.20)
        + (Seasonality × 0.10)

Each sub-score itself is 0-100.

Note: Competition is INVERTED in the formula because high competition is
bad for sellers. The CompetitionSignal.score field already stores the
inverted "less competition is higher" score, so we use it directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from scalemyprints.domain.niche.enums import (
    CompetitionLevel,
    NicheHealth,
    TrendDirection,
)
from scalemyprints.domain.niche.models import (
    CompetitionSignal,
    DemandSignal,
    ProfitabilitySignal,
    SeasonalitySignal,
    TrendSignal,
)


# Default weights — sum must equal 1.0
DEFAULT_WEIGHTS = {
    "demand": 0.35,
    "trend": 0.20,
    "competition": 0.15,
    "profitability": 0.20,
    "seasonality": 0.10,
}


@dataclass(frozen=True, slots=True)
class ScoringWeights:
    """User-tunable weights. Must sum to 1.0."""

    demand: float = 0.35
    trend: float = 0.20
    competition: float = 0.15
    profitability: float = 0.20
    seasonality: float = 0.10

    def __post_init__(self) -> None:
        total = self.demand + self.trend + self.competition + self.profitability + self.seasonality
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Weights must sum to 1.0 (got {total})")


# -----------------------------------------------------------------------------
# Sub-score builders — each translates raw data → 0-100
# -----------------------------------------------------------------------------


def build_demand_score(
    *,
    search_volume_index: int,
    listing_count: int | None,
    source: str,
) -> DemandSignal:
    """
    Demand = primarily search volume index.

    If marketplace listing_count is available, blend it in (more listings
    in a niche = some demand validation, but capped to avoid double-counting
    competition).
    """
    base = max(0, min(100, search_volume_index))

    if listing_count is not None and listing_count > 0:
        # Listings 1-100 → 0-25 bonus (logarithmic dampening)
        # Listings 100-1000 → 25-40 bonus
        # Listings 1000+ → 40 bonus (capped)
        if listing_count >= 1000:
            listing_bonus = 40
        elif listing_count >= 100:
            listing_bonus = 25 + ((listing_count - 100) / 900) * 15
        else:
            listing_bonus = (listing_count / 100) * 25

        # Blend: 70% trends, 30% listings
        blended = (base * 0.7) + (listing_bonus * 0.3)
        score = max(0, min(100, int(blended)))
    else:
        score = base

    return DemandSignal(
        score=score,
        search_volume_index=base,
        listing_count=listing_count,
        source=source,
    )


def build_trend_score(
    *,
    growth_pct_90d: float | None,
    sample_points: int,
) -> TrendSignal:
    """
    Trend score from 90-day growth percentage.

    Growth +50% or more  → score 90-100 (strongly rising)
    Growth +10% to +50%  → score 60-90 (rising)
    Growth -10% to +10%  → score 40-60 (stable)
    Growth -50% to -10%  → score 10-40 (declining)
    Growth -50% or less  → score 0-10 (collapsing)

    Insufficient data (sample_points < 3) → score 50 (neutral) with stable direction.
    """
    if sample_points < 3 or growth_pct_90d is None:
        return TrendSignal(
            score=50,
            direction=TrendDirection.STABLE,
            growth_pct_90d=growth_pct_90d,
            sample_points=sample_points,
        )

    g = growth_pct_90d

    if g >= 50:
        score = min(100, 90 + int((g - 50) / 5))
        direction = TrendDirection.RISING
    elif g >= 10:
        score = 60 + int((g - 10) * 0.75)  # 10→60, 50→90
        direction = TrendDirection.RISING
    elif g >= -10:
        score = 40 + int((g + 10))  # -10→40, +10→60
        direction = TrendDirection.STABLE
    elif g >= -50:
        score = max(10, 40 + int((g + 10) * 0.75))  # -10→40, -50→10
        direction = TrendDirection.DECLINING
    else:
        score = max(0, 10 + int((g + 50) / 10))
        direction = TrendDirection.DECLINING

    return TrendSignal(
        score=max(0, min(100, score)),
        direction=direction,
        growth_pct_90d=g,
        sample_points=sample_points,
    )


def build_competition_score(
    *,
    listing_count: int | None,
    unique_sellers_estimate: int | None,
    avg_listing_age_days: float | None,
) -> CompetitionSignal:
    """
    Competition score is INVERTED — higher score means LESS competition.

    Listings <100        → score 85-100 (LOW competition, good)
    Listings 100-1000    → score 50-85 (MEDIUM)
    Listings 1000-10000  → score 20-50 (HIGH)
    Listings 10000+      → score 0-20  (SATURATED, avoid)

    Adjustments:
    - Many unique sellers diluting market → +5 to score (less single-seller dominance)
    - Old listings only (avg age >365d) → +5 (newer entrants might still grow)
    """
    if listing_count is None:
        return CompetitionSignal(
            score=50,  # neutral when unknown
            level=CompetitionLevel.MEDIUM,
            listing_count=None,
            unique_sellers_estimate=unique_sellers_estimate,
            avg_listing_age_days=avg_listing_age_days,
        )

    if listing_count < 100:
        base = 100 - int((listing_count / 100) * 15)
        level = CompetitionLevel.LOW
    elif listing_count < 1000:
        base = 85 - int(((listing_count - 100) / 900) * 35)
        level = CompetitionLevel.MEDIUM
    elif listing_count < 10000:
        base = 50 - int(((listing_count - 1000) / 9000) * 30)
        level = CompetitionLevel.HIGH
    else:
        base = max(0, 20 - int((listing_count - 10000) / 5000))
        level = CompetitionLevel.SATURATED

    # Adjustments
    bonus = 0
    if unique_sellers_estimate is not None and listing_count > 0:
        seller_ratio = unique_sellers_estimate / listing_count
        if seller_ratio > 0.7:  # >70% unique sellers, fragmented
            bonus += 5

    if avg_listing_age_days is not None and avg_listing_age_days > 365:
        bonus += 5

    score = max(0, min(100, base + bonus))

    return CompetitionSignal(
        score=score,
        level=level,
        listing_count=listing_count,
        unique_sellers_estimate=unique_sellers_estimate,
        avg_listing_age_days=avg_listing_age_days,
    )


def build_profitability_score(
    *,
    avg_price_usd: float | None,
    sample_size: int,
    estimated_production_cost_usd: float = 8.0,
    estimated_fees_pct: float = 0.20,
) -> ProfitabilitySignal:
    """
    Profitability based on price - production - fees.

    Etsy fee model: ~6.5% transaction + ~3% payment + ~$0.20 listing.
    Amazon Merch: royalty model, ~13-18% of sale price.
    Default 20% fees is reasonable POD blended estimate.
    Production cost ~$8 typical for shirt/mug from PODservice.

    Margin > $15 → score 80-100
    Margin $8-15 → score 50-80
    Margin $3-8  → score 20-50
    Margin < $3  → score 0-20
    """
    if avg_price_usd is None or sample_size == 0:
        return ProfitabilitySignal(
            score=50,
            avg_price_usd=avg_price_usd,
            estimated_margin_usd=None,
            sample_size=sample_size,
        )

    margin = avg_price_usd * (1 - estimated_fees_pct) - estimated_production_cost_usd

    if margin >= 15:
        score = min(100, 80 + int((margin - 15) * 2))
    elif margin >= 8:
        score = 50 + int(((margin - 8) / 7) * 30)
    elif margin >= 3:
        score = 20 + int(((margin - 3) / 5) * 30)
    elif margin >= 0:
        score = int((margin / 3) * 20)
    else:
        score = 0

    return ProfitabilitySignal(
        score=max(0, min(100, score)),
        avg_price_usd=avg_price_usd,
        estimated_margin_usd=round(margin, 2),
        sample_size=sample_size,
    )


def build_seasonality_score(
    *,
    nearest_event_name: str | None,
    nearest_event_date: date | None,
    nearest_event_pod_relevance: int | None,
    as_of: date,
) -> SeasonalitySignal:
    """
    Higher score when a relevant POD event is approaching.

    Event in 0-7 days   → score 90-100 (last-chance window)
    Event in 8-30 days  → score 65-90  (sweet spot for design + listing)
    Event in 31-60 days → score 40-65  (early prep)
    Event in 61-90 days → score 20-40
    Event >90 days away → score 10-20
    No relevant event   → score 30 (baseline; always-evergreen niches still viable)
    """
    if nearest_event_date is None or nearest_event_pod_relevance is None:
        return SeasonalitySignal(
            score=30,
            nearest_event_name=None,
            nearest_event_date=None,
            days_until_event=None,
        )

    days_until = (nearest_event_date - as_of).days
    if days_until < 0:
        # event already passed; check next year same date
        days_until = days_until + 365

    relevance = nearest_event_pod_relevance / 100  # 0-1 multiplier

    if days_until <= 7:
        base = 95
    elif days_until <= 30:
        base = 65 + int(((30 - days_until) / 23) * 25)
    elif days_until <= 60:
        base = 40 + int(((60 - days_until) / 30) * 25)
    elif days_until <= 90:
        base = 20 + int(((90 - days_until) / 30) * 20)
    else:
        base = max(10, 20 - int((days_until - 90) / 30))

    # Scale by event's POD relevance
    score = max(0, min(100, int(base * relevance)))

    return SeasonalitySignal(
        score=score,
        nearest_event_name=nearest_event_name,
        nearest_event_date=nearest_event_date,
        days_until_event=days_until,
    )


# -----------------------------------------------------------------------------
# Top-line NHS aggregator
# -----------------------------------------------------------------------------


def calculate_nhs(
    *,
    demand: DemandSignal,
    trend: TrendSignal,
    competition: CompetitionSignal,
    profitability: ProfitabilitySignal,
    seasonality: SeasonalitySignal,
    weights: ScoringWeights | None = None,
) -> tuple[int, NicheHealth]:
    """
    Compute the headline Niche Health Score (0-100) and label.
    """
    w = weights or ScoringWeights()

    nhs = (
        demand.score * w.demand
        + trend.score * w.trend
        + competition.score * w.competition  # already inverted
        + profitability.score * w.profitability
        + seasonality.score * w.seasonality
    )

    nhs_int = max(0, min(100, int(round(nhs))))

    if nhs_int >= 75:
        health = NicheHealth.HOT
    elif nhs_int >= 55:
        health = NicheHealth.PROMISING
    elif nhs_int >= 40:
        health = NicheHealth.MODERATE
    elif nhs_int >= 20:
        health = NicheHealth.WEAK
    else:
        health = NicheHealth.AVOID

    return nhs_int, health
