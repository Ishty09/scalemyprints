"""
Pydantic models for the trademark domain.

IMPORTANT: These mirror packages/contracts/src/trademark.ts field-for-field.
When you change one, change the other and update the cross-boundary tests.

Design:
- All models are `model_config = ConfigDict(frozen=True)` — immutable
- Validation at boundaries via Pydantic, not manual checks
- Use `Annotated` for constrained types (not deprecated Field syntax in v2)
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from scalemyprints.domain.trademark.enums import (
    FilingStatus,
    JurisdictionCode,
    MonitorFrequency,
    RecommendationSeverity,
    RiskLevel,
)

# -----------------------------------------------------------------------------
# Type aliases
# -----------------------------------------------------------------------------

NiceClass = Annotated[int, Field(ge=1, le=45)]
"""Nice classification — integer 1-45."""

Score = Annotated[int, Field(ge=0, le=100)]
"""Risk score 0-100."""

Density = Annotated[float, Field(ge=0.0, le=1.0)]
"""Density score 0.0-1.0."""


# -----------------------------------------------------------------------------
# Shared base
# -----------------------------------------------------------------------------


class _FrozenModel(BaseModel):
    """Base for immutable domain models."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True, extra="forbid")


# -----------------------------------------------------------------------------
# Individual trademark record (one hit from a jurisdiction search)
# -----------------------------------------------------------------------------


class TrademarkRecord(_FrozenModel):
    """A single trademark filing record."""

    registration_number: str
    mark: str
    owner: str | None
    status: FilingStatus
    raw_status: str | None
    nice_class: NiceClass | None
    nice_classes: list[NiceClass]
    filing_date: str | None
    registration_date: str | None
    jurisdiction: JurisdictionCode
    source_url: str | None
    goods_services: str | None
    is_active: bool
    is_pending: bool


# -----------------------------------------------------------------------------
# Per-jurisdiction risk analysis
# -----------------------------------------------------------------------------


class JurisdictionRisk(_FrozenModel):
    code: JurisdictionCode
    risk_score: Score
    risk_level: RiskLevel
    active_registrations: int = Field(ge=0)
    pending_applications: int = Field(ge=0)
    adjacent_class_registrations: int = Field(ge=0)
    common_law_density: Density | None
    arbitrage_available: bool
    matching_records: list[TrademarkRecord]
    search_duration_ms: int | None = Field(default=None, ge=0)
    error: str | None = None


# -----------------------------------------------------------------------------
# Request
# -----------------------------------------------------------------------------


class TrademarkSearchRequest(BaseModel):
    """Search request from the frontend."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    phrase: Annotated[str, Field(min_length=1, max_length=200)]
    jurisdictions: Annotated[list[JurisdictionCode], Field(min_length=1)] = Field(
        default_factory=lambda: [JurisdictionCode.US, JurisdictionCode.EU, JurisdictionCode.AU]
    )
    nice_classes: Annotated[list[NiceClass], Field(min_length=1)] = Field(
        default_factory=lambda: [25, 21]
    )
    check_common_law: bool = True

    @field_validator("jurisdictions", "nice_classes")
    @classmethod
    def _dedupe(cls, v: list) -> list:
        """Remove duplicates while preserving order."""
        seen: set = set()
        out: list = []
        for item in v:
            if item not in seen:
                seen.add(item)
                out.append(item)
        return out


# -----------------------------------------------------------------------------
# Recommendation
# -----------------------------------------------------------------------------


class TrademarkRecommendation(_FrozenModel):
    severity: RecommendationSeverity
    message: str
    action: str | None


# -----------------------------------------------------------------------------
# Response
# -----------------------------------------------------------------------------


class TrademarkSearchResponse(_FrozenModel):
    phrase: str
    overall_risk_score: Score
    overall_risk_level: RiskLevel
    jurisdictions: list[JurisdictionRisk]
    recommendations: list[TrademarkRecommendation]
    phrase_genericness: Density
    nice_classes_searched: list[NiceClass]
    analyzed_at: datetime
    from_cache: bool
    duration_ms: int = Field(ge=0)


# -----------------------------------------------------------------------------
# Monitors
# -----------------------------------------------------------------------------


class TrademarkMonitor(_FrozenModel):
    id: UUID
    user_id: UUID
    phrase: str
    jurisdictions: list[JurisdictionCode]
    nice_classes: list[NiceClass]
    frequency: MonitorFrequency
    alert_email: str | None
    alert_webhook_url: str | None
    is_active: bool
    last_checked_at: datetime | None
    created_at: datetime


class CreateMonitorRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    phrase: Annotated[str, Field(min_length=1, max_length=200)]
    jurisdictions: Annotated[list[JurisdictionCode], Field(min_length=1)]
    nice_classes: Annotated[list[NiceClass], Field(min_length=1)]
    frequency: MonitorFrequency = MonitorFrequency.WEEKLY
    alert_email: str | None = None


# -----------------------------------------------------------------------------
# History
# -----------------------------------------------------------------------------


class SearchHistoryItem(_FrozenModel):
    id: UUID
    phrase: str
    overall_risk_score: Score
    overall_risk_level: RiskLevel
    jurisdictions_searched: list[JurisdictionCode]
    analyzed_at: datetime
