"""
Trademark + Opportunity overlay.

The killer combinator: given a listing URL or phrase, fuse the Spy
signals (velocity, saturation, sales estimate) with the existing
Trademark risk score. The result tells a seller in one shot:

  "This phrase has 5K sales/month BUT is filed in IC25 with HIGH risk."

vs

  "Open niche with no TM hits across US/EU/AU — go for it."

Input: phrase (plus optional listing URL for context)
Output: TMOverlayResult with:
  - opportunity_score (0-100, derived from Spy data)
  - risk_score (0-100, from TrademarkSearchService)
  - combined_verdict: "go" | "caution" | "block"
  - per-jurisdiction risk + sample hits
  - velocity / saturation summary
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.spy import saturation_service
from scalemyprints.domain.spy.enums import Marketplace

if TYPE_CHECKING:
    from scalemyprints.domain.spy.search_service import SpySearchService
    from scalemyprints.domain.trademark.models import (
        TrademarkSearchRequest,
        TrademarkSearchResponse,
    )
    from scalemyprints.domain.trademark.search_service import TrademarkSearchService

logger = get_logger(__name__)


class TMOverlayResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    phrase: str
    opportunity_score: int = Field(ge=0, le=100)
    risk_score: int = Field(ge=0, le=100)
    saturation_score: int = Field(ge=0, le=100)
    combined_verdict: str  # "go" | "caution" | "block"
    listings_count: int = Field(ge=0)
    est_monthly_gmv_usd: float = Field(ge=0.0)
    trademark: dict[str, object] = Field(default_factory=dict)
    duration_ms: int = Field(ge=0)


class TMOverlayService:
    """Fuses Spy + TM modules."""

    def __init__(
        self,
        *,
        spy_search: SpySearchService,
        trademark_search: TrademarkSearchService,
    ) -> None:
        self._spy = spy_search
        self._tm = trademark_search

    async def overlay(
        self,
        *,
        phrase: str,
        marketplaces: list[Marketplace] | None = None,
        per_marketplace_limit: int = 30,
        nice_classes: list[int] | None = None,
    ) -> TMOverlayResult:
        start = time.monotonic()

        # Fan out — spy + TM in parallel
        import asyncio  # noqa: PLC0415

        from scalemyprints.domain.spy.models import SpyQuery  # noqa: PLC0415
        from scalemyprints.domain.trademark.enums import JurisdictionCode  # noqa: PLC0415
        from scalemyprints.domain.trademark.models import (  # noqa: PLC0415
            TrademarkSearchRequest,
        )

        spy_task = self._spy.run(
            SpyQuery(
                text=phrase,
                marketplaces=marketplaces or [],
                limit=per_marketplace_limit,
            )
        )
        tm_task = self._tm.search(
            TrademarkSearchRequest(
                phrase=phrase,
                jurisdictions=[
                    JurisdictionCode.US,
                    JurisdictionCode.EU,
                    JurisdictionCode.AU,
                ],
                nice_classes=nice_classes or [25, 21],
                check_common_law=False,
            )
        )

        spy_result, tm_result = await asyncio.gather(
            spy_task, tm_task, return_exceptions=False
        )

        # ---- Saturation + opportunity --------------------------------------
        sat = saturation_service.compute(spy_result.listings, phrase=phrase)
        gmv = sum(
            (l.est_daily_sales or 0.0) * (l.price_usd or 0.0) * 30.0
            for l in spy_result.listings
        )

        # Opportunity = inverse of saturation, scaled by GMV signal
        # 0-saturation niche with $0 GMV: 50 (uncertain). 0-saturation
        # with high GMV: 95. High-saturation with high GMV: 30 (red ocean).
        opportunity = _opportunity(sat.score, gmv)

        # ---- TM risk + verdict ---------------------------------------------
        risk = tm_result.overall_risk_score
        verdict = _verdict(opportunity, risk)

        return TMOverlayResult(
            phrase=phrase,
            opportunity_score=opportunity,
            risk_score=risk,
            saturation_score=sat.score,
            combined_verdict=verdict,
            listings_count=sat.listings_count,
            est_monthly_gmv_usd=round(gmv, 2),
            trademark=_tm_to_summary(tm_result),
            duration_ms=int((time.monotonic() - start) * 1000),
        )


def _opportunity(saturation: int, gmv_usd: float) -> int:
    """
    Translate saturation + GMV signal into an opportunity score.

    - Pure saturation (0 = wide open) → 70-95 if there's GMV evidence
    - Saturation=50, GMV=$0 → 40 (neither demand nor space)
    - Saturation=80 → low opportunity regardless of GMV (red ocean)
    """
    base = max(0, 100 - saturation)
    if gmv_usd <= 0:
        # No demand signal at all — pull score down toward middle
        base = max(30, base - 20)
    elif gmv_usd >= 5000:
        # Strong demand signal — bump
        base = min(100, base + 10)
    return max(0, min(100, base))


def _verdict(opportunity: int, risk: int) -> str:
    if risk >= 75:
        return "block"
    if risk >= 50 or opportunity < 30:
        return "caution"
    return "go"


def _tm_to_summary(tm: TrademarkSearchResponse) -> dict[str, object]:
    """Strip TrademarkSearchResponse to a compact dict for the overlay."""
    return {
        "overall_risk_level": tm.overall_risk_level.value,
        "overall_risk_score": tm.overall_risk_score,
        "jurisdictions": [
            {
                "code": j.code.value,
                "risk_score": j.risk_score,
                "risk_level": j.risk_level.value,
                "match_count": j.match_count,
                "error": j.error,
            }
            for j in tm.jurisdictions
        ],
        "recommendations": [
            {
                "severity": r.severity.value,
                "message": r.message,
            }
            for r in tm.recommendations[:3]
        ],
    }
