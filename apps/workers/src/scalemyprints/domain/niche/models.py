"""
Niche Radar — domain models.

All models frozen (immutable). Pure data shapes; no behavior.
Behavior lives in services (scoring_service, events_service, etc.).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from scalemyprints.domain.niche.enums import (
    CompetitionLevel,
    Country,
    EventCategory,
    NicheHealth,
    TrendDirection,
)

NicheScore = Annotated[int, Field(ge=0, le=100)]


# -----------------------------------------------------------------------------
# Sub-scores — each captures one dimension of niche viability
# -----------------------------------------------------------------------------


class DemandSignal(BaseModel):
    """Search/listing-volume snapshot for a niche."""

    model_config = ConfigDict(frozen=True)

    score: NicheScore
    search_volume_index: int  # 0-100 normalized from Google Trends
    listing_count: int | None  # marketplace count, None if unavailable
    source: str  # "google_trends" | "apify_etsy" | "fallback"


class TrendSignal(BaseModel):
    """Direction + magnitude of niche momentum."""

    model_config = ConfigDict(frozen=True)

    score: NicheScore
    direction: TrendDirection
    growth_pct_90d: float | None  # % change, None if insufficient data
    sample_points: int  # data points used for trend calc


class CompetitionSignal(BaseModel):
    """Saturation analysis."""

    model_config = ConfigDict(frozen=True)

    score: NicheScore  # higher = LESS competition (better for sellers)
    level: CompetitionLevel
    listing_count: int | None
    unique_sellers_estimate: int | None
    avg_listing_age_days: float | None


class ProfitabilitySignal(BaseModel):
    """Earnings potential per sale."""

    model_config = ConfigDict(frozen=True)

    score: NicheScore
    avg_price_usd: float | None
    estimated_margin_usd: float | None  # after fees + production
    sample_size: int


class SeasonalitySignal(BaseModel):
    """Event/season proximity boost."""

    model_config = ConfigDict(frozen=True)

    score: NicheScore
    nearest_event_name: str | None
    nearest_event_date: date | None
    days_until_event: int | None


# -----------------------------------------------------------------------------
# Event — calendar entry that drives demand
# -----------------------------------------------------------------------------


class Event(BaseModel):
    """A date in a country's calendar relevant to POD."""

    model_config = ConfigDict(frozen=True)

    id: str  # e.g., "us-2026-05-10-mothers-day"
    country: Country
    event_date: date
    name: str
    category: EventCategory
    description: str | None = None
    pod_relevance_score: NicheScore  # 0-100, curated
    suggested_niches: list[str] = Field(default_factory=list)


# -----------------------------------------------------------------------------
# Niche record — main output of a search
# -----------------------------------------------------------------------------


class NicheRecord(BaseModel):
    """
    A single niche analyzed across all signals.

    `nhs_score` is the headline number (0-100).
    Sub-signals provide the breakdown for UI rendering.
    """

    model_config = ConfigDict(frozen=True)

    keyword: str
    country: Country
    nhs_score: NicheScore
    health: NicheHealth

    demand: DemandSignal
    trend: TrendSignal
    competition: CompetitionSignal
    profitability: ProfitabilitySignal
    seasonality: SeasonalitySignal

    related_keywords: list[str] = Field(default_factory=list)
    sample_listings_urls: list[str] = Field(default_factory=list)
    upcoming_events: list[Event] = Field(default_factory=list)

    analyzed_at: datetime
    duration_ms: int
    data_sources_used: list[str]  # provenance for debugging
    degraded: bool = False  # True if some sources failed
