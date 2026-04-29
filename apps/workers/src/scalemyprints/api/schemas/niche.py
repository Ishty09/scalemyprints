"""
Niche Radar API schemas.

Request/response shapes for the niche endpoints. Domain models
(NicheRecord, Event) re-used directly — the envelope wraps them.
"""

from __future__ import annotations

from datetime import date as date_type

from pydantic import BaseModel, ConfigDict, Field

from scalemyprints.domain.niche.enums import Country, EventCategory


# -----------------------------------------------------------------------------
# Search
# -----------------------------------------------------------------------------


class NicheSearchRequest(BaseModel):
    """User-submitted niche search."""

    model_config = ConfigDict(extra="forbid")

    keyword: str = Field(..., min_length=2, max_length=80)
    country: Country = Country.US


# -----------------------------------------------------------------------------
# Events
# -----------------------------------------------------------------------------


class EventsListRequest(BaseModel):
    """Optional query params for /events."""

    model_config = ConfigDict(extra="forbid")

    country: Country = Country.US
    from_date: date_type | None = Field(None, alias="from")
    to_date: date_type | None = Field(None, alias="to")
    category: EventCategory | None = None


class EventListItem(BaseModel):
    """Slim event shape for list endpoints (vs full Event with niches)."""

    model_config = ConfigDict(frozen=True)

    id: str
    country: Country
    event_date: date_type
    name: str
    category: EventCategory
    pod_relevance_score: int
    suggested_niches: list[str]
    days_until: int  # convenience computed field


# -----------------------------------------------------------------------------
# Niche expansion (LLM)
# -----------------------------------------------------------------------------


class NicheExpansionRequest(BaseModel):
    """Generate sub-niches from a seed keyword."""

    model_config = ConfigDict(extra="forbid")

    seed_keyword: str = Field(..., min_length=2, max_length=80)
    country: Country = Country.US
    max_suggestions: int = Field(default=20, ge=5, le=30)


class NicheExpansionResponse(BaseModel):
    """LLM expansion result."""

    model_config = ConfigDict(frozen=True)

    seed_keyword: str
    country: Country
    suggestions: list[str]
    rationale: str | None = None
    duration_ms: int
