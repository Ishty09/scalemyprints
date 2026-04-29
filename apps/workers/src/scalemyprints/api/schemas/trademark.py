"""
Trademark API request/response DTOs.

These are thin wrappers over domain models. We intentionally re-export
domain types (TrademarkSearchResponse, etc.) rather than duplicate them
when no HTTP-specific shaping is needed.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from scalemyprints.domain.trademark.enums import JurisdictionCode, MonitorFrequency
from scalemyprints.domain.trademark.models import (
    NiceClass,
    SearchHistoryItem,
    TrademarkMonitor,
    TrademarkSearchResponse,
)


# -----------------------------------------------------------------------------
# Request bodies
# -----------------------------------------------------------------------------


class SearchBody(BaseModel):
    """
    POST /api/v1/trademark/search body.

    Matches TrademarkSearchRequest in the domain but stays in the API layer
    so any HTTP-specific alias/casing changes don't leak into domain.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    phrase: Annotated[str, Field(min_length=1, max_length=200)]
    jurisdictions: Annotated[list[JurisdictionCode], Field(min_length=1)] = Field(
        default_factory=lambda: [JurisdictionCode.US, JurisdictionCode.EU, JurisdictionCode.AU]
    )
    nice_classes: Annotated[list[NiceClass], Field(min_length=1)] = Field(
        default_factory=lambda: [25, 21]
    )
    check_common_law: bool = True


class CreateMonitorBody(BaseModel):
    """POST /api/v1/trademark/monitors body."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    phrase: Annotated[str, Field(min_length=1, max_length=200)]
    jurisdictions: Annotated[list[JurisdictionCode], Field(min_length=1)]
    nice_classes: Annotated[list[NiceClass], Field(min_length=1)]
    frequency: MonitorFrequency = MonitorFrequency.WEEKLY
    alert_email: str | None = None


# -----------------------------------------------------------------------------
# Response payloads
# -----------------------------------------------------------------------------

# These are just domain types re-exported under API names for consistency.
# They're wrapped in ApiResponse<T> at the route level.
SearchResponse = TrademarkSearchResponse
MonitorResponse = TrademarkMonitor


class SearchHistoryResponse(BaseModel):
    """GET /api/v1/trademark/history response payload."""

    model_config = ConfigDict(frozen=True)

    searches: list[SearchHistoryItem]
    total: int = Field(ge=0)
