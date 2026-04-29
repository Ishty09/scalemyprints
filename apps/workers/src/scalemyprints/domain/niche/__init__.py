"""Niche Radar domain layer."""

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
from scalemyprints.domain.niche.ports import (
    EventsProvider,
    MarketplaceData,
    MarketplaceProvider,
    NicheCacheStore,
    NicheExpander,
    NicheExpansionResult,
    TrendsData,
    TrendsProvider,
)
from scalemyprints.domain.niche.scoring_service import (
    DEFAULT_WEIGHTS,
    ScoringWeights,
    build_competition_score,
    build_demand_score,
    build_profitability_score,
    build_seasonality_score,
    build_trend_score,
    calculate_nhs,
)
from scalemyprints.domain.niche.search_service import NicheSearchService

__all__ = [
    "DEFAULT_WEIGHTS",
    "CompetitionLevel",
    "CompetitionSignal",
    "Country",
    "DemandSignal",
    "Event",
    "EventCategory",
    "EventsProvider",
    "MarketplaceData",
    "MarketplaceProvider",
    "NicheCacheStore",
    "NicheExpander",
    "NicheExpansionResult",
    "NicheHealth",
    "NicheRecord",
    "NicheSearchService",
    "ProfitabilitySignal",
    "ScoringWeights",
    "SeasonalitySignal",
    "TrendDirection",
    "TrendSignal",
    "TrendsData",
    "TrendsProvider",
    "build_competition_score",
    "build_demand_score",
    "build_profitability_score",
    "build_seasonality_score",
    "build_trend_score",
    "calculate_nhs",
]
