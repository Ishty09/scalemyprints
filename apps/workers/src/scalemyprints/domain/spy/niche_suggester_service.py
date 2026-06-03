"""
AI Niche Suggester.

Given an optional set of user constraints (preferred styles, excluded
phrases), return a ranked list of N niche suggestions sourced from:
- The hot-movers feed (velocity-driven)
- The viral-mining feed (trending-driven)
- Tag mining (long-tail co-occurrence)

Each candidate is run through the TM overlay so we don't surface
phrases with high trademark risk. Final ranking blends opportunity
× pod-readiness × (1 - risk/100).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.spy.watchlist_models import NicheSuggestion

if TYPE_CHECKING:
    from scalemyprints.domain.spy.enums import Marketplace
    from scalemyprints.domain.spy.tm_overlay_service import TMOverlayService
    from scalemyprints.domain.spy.viral_mining_service import ViralMiningService
    from scalemyprints.infrastructure.spy_storage.hot_movers import HotMoversProvider

logger = get_logger(__name__)


class NicheSuggesterInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preferred_styles: list[str] = Field(default_factory=list)
    excluded_phrases: list[str] = Field(default_factory=list)
    marketplaces: list[Marketplace] = Field(default_factory=list)
    limit: int = Field(default=10, ge=1, le=50)
    min_pod_readiness: int = Field(default=55, ge=0, le=100)
    max_risk: int = Field(default=60, ge=0, le=100)


class NicheSuggesterResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    suggestions: list[NicheSuggestion] = Field(default_factory=list)
    candidates_considered: int = Field(ge=0)
    duration_ms: int = Field(ge=0)


class NicheSuggesterService:
    """Cross-source ranker that produces actionable niche picks."""

    def __init__(
        self,
        *,
        viral_mining: ViralMiningService,
        hot_movers: HotMoversProvider,
        tm_overlay: TMOverlayService,
    ) -> None:
        self._viral = viral_mining
        self._hot = hot_movers
        self._tm = tm_overlay

    async def suggest(self, payload: NicheSuggesterInput) -> NicheSuggesterResult:
        start = time.monotonic()

        excluded = {p.strip().lower() for p in payload.excluded_phrases}
        seen: set[str] = set()

        # ---- 1. Pull candidate phrases from both sources -------------------
        candidates: list[tuple[str, str, list[str]]] = []  # (phrase, source, styles)

        # Viral mining feed
        viral = await self._viral.run(
            per_source_limit=40,
            total_limit=80,
            min_pod_readiness=payload.min_pod_readiness,
            classify=True,
        )
        for sig in viral.signals:
            key = sig.phrase.strip().lower()
            if not key or key in excluded or key in seen:
                continue
            seen.add(key)
            candidates.append((sig.phrase, "viral", sig.suggested_styles))

        # Hot movers feed → use title as the phrase
        hot_movers = await self._hot.recent(limit=40)
        for item in hot_movers:
            phrase = (item.title or "").strip()
            key = phrase.lower()
            if not phrase or key in excluded or key in seen:
                continue
            seen.add(key)
            candidates.append((phrase, "hot_movers", []))

        # ---- 2. Score each via TM overlay (parallel, bounded) -------------
        import asyncio  # noqa: PLC0415

        sem = asyncio.Semaphore(6)

        async def _score(phrase: str, source: str, styles: list[str]) -> NicheSuggestion | None:
            async with sem:
                overlay = await self._tm.overlay(
                    phrase=phrase,
                    marketplaces=payload.marketplaces,
                )
            if overlay.risk_score > payload.max_risk:
                return None
            pod_score = 75 if source == "viral" else 60  # heuristic; viral is pre-filtered
            return NicheSuggestion(
                phrase=phrase,
                opportunity_score=overlay.opportunity_score,
                risk_score=overlay.risk_score,
                saturation_score=overlay.saturation_score,
                pod_readiness_score=pod_score,
                est_monthly_gmv_usd=overlay.est_monthly_gmv_usd,
                suggested_styles=styles or payload.preferred_styles[:3],
                rationale=(
                    f"opportunity={overlay.opportunity_score}, "
                    f"risk={overlay.risk_score}, "
                    f"saturation={overlay.saturation_score} "
                    f"(verdict={overlay.combined_verdict})"
                ),
                source=source,
                sample_urls=[],
            )

        scored = await asyncio.gather(*(_score(*c) for c in candidates))
        suggestions = [s for s in scored if s is not None]

        # ---- 3. Final ranking ---------------------------------------------
        def _blend(s: NicheSuggestion) -> float:
            risk_factor = 1.0 - (s.risk_score / 100.0)
            return s.opportunity_score * (s.pod_readiness_score / 100.0) * risk_factor

        suggestions.sort(key=_blend, reverse=True)

        return NicheSuggesterResult(
            suggestions=suggestions[: payload.limit],
            candidates_considered=len(candidates),
            duration_ms=int((time.monotonic() - start) * 1000),
        )
