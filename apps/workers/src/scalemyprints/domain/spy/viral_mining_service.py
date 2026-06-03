"""
Viral mining orchestrator.

Fan-out across every configured ViralSourceAdapter (Reddit / TikTok /
Twitter), then enrich each candidate signal with the PODReadinessClassifier
so the UI can filter to "things that would actually become POD products."

Outputs a ranked list of ViralSignal (highest pod_readiness × momentum
first). De-duplicates phrases across sources.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.spy.models import ViralSignal

if TYPE_CHECKING:
    from scalemyprints.domain.spy.ports import ViralSourceAdapter
    from scalemyprints.infrastructure.llm.pod_readiness_classifier import (
        PODReadinessClassifier,
    )

logger = get_logger(__name__)


class ViralMiningResult(BaseModel):
    """Output of ViralMiningService.run()."""

    model_config = ConfigDict(frozen=True)

    signals: list[ViralSignal] = Field(default_factory=list)
    sources_used: list[str] = Field(default_factory=list)
    sources_failed: list[tuple[str, str]] = Field(default_factory=list)
    duration_ms: int = Field(ge=0)


class ViralMiningService:
    """Coordinates fan-out + POD-readiness enrichment."""

    def __init__(
        self,
        *,
        sources: list[ViralSourceAdapter],
        classifier: PODReadinessClassifier,
    ) -> None:
        self._sources = sources
        self._classifier = classifier

    async def run(
        self,
        *,
        per_source_limit: int = 30,
        total_limit: int = 60,
        min_pod_readiness: int = 50,
        classify: bool = True,
    ) -> ViralMiningResult:
        start = time.monotonic()
        if not self._sources:
            return ViralMiningResult(duration_ms=0)

        # ---- 1. Fan out -----------------------------------------------------
        results = await asyncio.gather(
            *(s.fetch(limit=per_source_limit) for s in self._sources),
            return_exceptions=True,
        )

        sources_used: list[str] = []
        sources_failed: list[tuple[str, str]] = []
        all_signals: list[ViralSignal] = []

        for adapter, raw in zip(self._sources, results, strict=True):
            src = adapter.source.value
            if isinstance(raw, BaseException):
                sources_failed.append((src, f"raised: {type(raw).__name__}"))
                continue
            if raw.error:
                sources_failed.append((src, raw.error))
                continue
            sources_used.append(src)
            all_signals.extend(raw.signals)

        # ---- 2. De-dupe by normalized phrase -------------------------------
        deduped: dict[str, ViralSignal] = {}
        for sig in all_signals:
            key = _normalize(sig.phrase)
            if not key:
                continue
            prev = deduped.get(key)
            if prev is None or sig.momentum_score > prev.momentum_score:
                deduped[key] = sig

        # ---- 3. Classify (POD-readiness) ----------------------------------
        candidates = list(deduped.values())
        if classify and candidates:
            phrases = [s.phrase for s in candidates]
            classifications = await self._classifier.classify_batch(phrases)
            enriched: list[ViralSignal] = []
            for sig, c in zip(candidates, classifications, strict=True):
                enriched.append(
                    sig.model_copy(
                        update={
                            "pod_readiness_score": c.score,
                            "suggested_styles": c.suggested_styles,
                            "note": (
                                f"{sig.note} • {c.reasoning}"
                                if sig.note
                                else c.reasoning
                            )[:400],
                        }
                    )
                )
            candidates = enriched

        # ---- 4. Filter + rank ---------------------------------------------
        filtered = [s for s in candidates if s.pod_readiness_score >= min_pod_readiness]
        filtered.sort(
            key=lambda s: (s.pod_readiness_score, s.momentum_score),
            reverse=True,
        )

        return ViralMiningResult(
            signals=filtered[:total_limit],
            sources_used=sources_used,
            sources_failed=sources_failed,
            duration_ms=int((time.monotonic() - start) * 1000),
        )


def _normalize(phrase: str) -> str:
    return (phrase or "").strip().lower()
