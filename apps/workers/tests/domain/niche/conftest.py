"""Shared fixtures for Niche Radar tests."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from scalemyprints.domain.niche.enums import (
    CompetitionLevel,
    Country,
    EventCategory,
    NicheHealth,
    TrendDirection,
)
from scalemyprints.domain.niche.models import (
    CompetitionSignal,
    DemandSignal,
    Event,
    NicheRecord,
    ProfitabilitySignal,
    SeasonalitySignal,
    TrendSignal,
)


@pytest.fixture
def sample_event() -> Event:
    return Event(
        id="us-2026-05-10-mothers-day",
        country=Country.US,
        event_date=date(2026, 5, 10),
        name="Mother's Day",
        category=EventCategory.CULTURAL,
        pod_relevance_score=100,
        suggested_niches=["mom mug", "mama shirt", "best mom"],
    )


@pytest.fixture
def sample_demand_high() -> DemandSignal:
    return DemandSignal(
        score=85,
        search_volume_index=80,
        listing_count=500,
        source="google_trends",
    )


@pytest.fixture
def sample_trend_rising() -> TrendSignal:
    return TrendSignal(
        score=80,
        direction=TrendDirection.RISING,
        growth_pct_90d=35.0,
        sample_points=12,
    )


@pytest.fixture
def sample_competition_low() -> CompetitionSignal:
    return CompetitionSignal(
        score=85,
        level=CompetitionLevel.LOW,
        listing_count=80,
        unique_sellers_estimate=70,
        avg_listing_age_days=120.0,
    )


@pytest.fixture
def sample_profitability_good() -> ProfitabilitySignal:
    return ProfitabilitySignal(
        score=70,
        avg_price_usd=24.99,
        estimated_margin_usd=11.99,
        sample_size=20,
    )


@pytest.fixture
def sample_seasonality_close() -> SeasonalitySignal:
    return SeasonalitySignal(
        score=85,
        nearest_event_name="Mother's Day",
        nearest_event_date=date(2026, 5, 10),
        days_until_event=13,
    )


@pytest.fixture
def sample_niche_record(
    sample_demand_high,
    sample_trend_rising,
    sample_competition_low,
    sample_profitability_good,
    sample_seasonality_close,
) -> NicheRecord:
    return NicheRecord(
        keyword="dog mom",
        country=Country.US,
        nhs_score=78,
        health=NicheHealth.HOT,
        demand=sample_demand_high,
        trend=sample_trend_rising,
        competition=sample_competition_low,
        profitability=sample_profitability_good,
        seasonality=sample_seasonality_close,
        related_keywords=["dog mama", "rescue mom"],
        sample_listings_urls=[],
        upcoming_events=[],
        analyzed_at=datetime.now(timezone.utc),
        duration_ms=1234,
        data_sources_used=["trends:ok", "marketplace:ok"],
        degraded=False,
    )
