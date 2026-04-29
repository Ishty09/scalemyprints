"""
Enums for the trademark domain.

These MUST match the corresponding Zod enums in
packages/contracts/src/trademark.ts field-for-field.
"""

from __future__ import annotations

from enum import StrEnum


class JurisdictionCode(StrEnum):
    US = "US"
    EU = "EU"
    UK = "UK"
    AU = "AU"


class RiskLevel(StrEnum):
    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FilingStatus(StrEnum):
    REGISTERED = "registered"
    PENDING = "pending"
    OPPOSED = "opposed"
    ABANDONED = "abandoned"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


class MonitorFrequency(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class RecommendationSeverity(StrEnum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    DANGER = "danger"


# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------

ACTIVE_STATUSES: frozenset[FilingStatus] = frozenset({FilingStatus.REGISTERED, FilingStatus.OPPOSED})
PENDING_STATUSES: frozenset[FilingStatus] = frozenset({FilingStatus.PENDING})

# POD-relevant Nice classifications with descriptions
POD_NICE_CLASSES: dict[int, str] = {
    9: "Electronics, phone cases",
    14: "Jewelry",
    16: "Paper goods, stickers, prints",
    18: "Bags, leather goods",
    20: "Furniture, pillows",
    21: "Drinkware (mugs, tumblers)",
    24: "Textiles, blankets",
    25: "Apparel (t-shirts, hoodies)",
    28: "Toys, games",
    41: "Education, entertainment",
}

# Adjacencies — classes that are legally considered "related" for confusion analysis
NICE_CLASS_ADJACENCIES: dict[int, frozenset[int]] = {
    25: frozenset({24, 18, 14, 9}),   # Apparel → textiles, bags, jewelry, phone cases
    21: frozenset({20, 8, 11}),        # Drinkware → furniture, hand tools, lighting
    16: frozenset({28, 41}),           # Paper goods → toys, education
    28: frozenset({16, 25}),           # Toys → paper, apparel
    9: frozenset({25, 14}),            # Phone cases → apparel, jewelry
    14: frozenset({25, 9}),            # Jewelry → apparel, phone cases
}


def get_adjacent_classes(target_classes: list[int]) -> frozenset[int]:
    """Return all Nice classes adjacent to the given target classes."""
    adjacent: set[int] = set()
    for tc in target_classes:
        adjacent.update(NICE_CLASS_ADJACENCIES.get(tc, frozenset()))
    # Remove target classes themselves — adjacency means "related but not the same"
    adjacent.difference_update(target_classes)
    return frozenset(adjacent)


def score_to_risk_level(score: int) -> RiskLevel:
    """Map numeric score [0-100] to RiskLevel. Must match TS scoreToRiskLevel."""
    if score <= 20:
        return RiskLevel.SAFE
    if score <= 40:
        return RiskLevel.LOW
    if score <= 60:
        return RiskLevel.MEDIUM
    if score <= 80:
        return RiskLevel.HIGH
    return RiskLevel.CRITICAL
