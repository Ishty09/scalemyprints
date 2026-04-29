"""
Trademark Shield domain.

The domain contains pure business logic for trademark risk analysis:
- Models (Pydantic — mirror TS contracts)
- Enums (jurisdictions, risk levels, filing statuses)
- Ports (protocols for external dependencies)
- Risk scorer (pure algorithm)
- Genericness calculator (heuristic)
- Recommendation generator (rules-based)
- Search service (orchestrator)

This module has ZERO I/O. All external calls go through Port protocols
which are implemented in the infrastructure layer.
"""

from scalemyprints.domain.trademark.enums import (
    ACTIVE_STATUSES,
    NICE_CLASS_ADJACENCIES,
    PENDING_STATUSES,
    POD_NICE_CLASSES,
    FilingStatus,
    JurisdictionCode,
    MonitorFrequency,
    RecommendationSeverity,
    RiskLevel,
    get_adjacent_classes,
    score_to_risk_level,
)
from scalemyprints.domain.trademark.genericness import GenericnessCalculator
from scalemyprints.domain.trademark.models import (
    CreateMonitorRequest,
    JurisdictionRisk,
    SearchHistoryItem,
    TrademarkMonitor,
    TrademarkRecommendation,
    TrademarkRecord,
    TrademarkSearchRequest,
    TrademarkSearchResponse,
)
from scalemyprints.domain.trademark.ports import (
    CacheStore,
    CommonLawChecker,
    TrademarkAPI,
    TrademarkSearchResult,
)
from scalemyprints.domain.trademark.recommender import RecommendationGenerator
from scalemyprints.domain.trademark.scorer import DEFAULT_WEIGHTS, RiskScorer, ScoringWeights
from scalemyprints.domain.trademark.search_service import (
    CACHE_TTL_SECONDS,
    SearchServiceConfig,
    TrademarkSearchService,
)

__all__ = [
    # Enums & constants
    "ACTIVE_STATUSES",
    "NICE_CLASS_ADJACENCIES",
    "PENDING_STATUSES",
    "POD_NICE_CLASSES",
    "FilingStatus",
    "JurisdictionCode",
    "MonitorFrequency",
    "RecommendationSeverity",
    "RiskLevel",
    "get_adjacent_classes",
    "score_to_risk_level",
    # Models
    "CreateMonitorRequest",
    "JurisdictionRisk",
    "SearchHistoryItem",
    "TrademarkMonitor",
    "TrademarkRecommendation",
    "TrademarkRecord",
    "TrademarkSearchRequest",
    "TrademarkSearchResponse",
    # Ports
    "CacheStore",
    "CommonLawChecker",
    "TrademarkAPI",
    "TrademarkSearchResult",
    # Services
    "DEFAULT_WEIGHTS",
    "GenericnessCalculator",
    "RecommendationGenerator",
    "RiskScorer",
    "ScoringWeights",
    # Orchestrator
    "CACHE_TTL_SECONDS",
    "SearchServiceConfig",
    "TrademarkSearchService",
]
