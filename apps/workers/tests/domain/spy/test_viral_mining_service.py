"""ViralMiningService — fan-out + dedupe + POD-readiness enrichment."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from scalemyprints.domain.spy.enums import ViralSource
from scalemyprints.domain.spy.models import ViralSignal
from scalemyprints.domain.spy.ports import (
    ViralFetchResult,
    ViralSourceAdapter,
)
from scalemyprints.domain.spy.viral_mining_service import ViralMiningService
from scalemyprints.infrastructure.llm.pod_readiness_classifier import (
    HeuristicPODReadinessClassifier,
    PODReadinessResult,
    PODReadinessClassifier,
)


class _FakeSource(ViralSourceAdapter):
    def __init__(
        self,
        source: ViralSource,
        signals: list[ViralSignal] | None = None,
        error: str | None = None,
    ) -> None:
        self._source = source
        self._signals = signals or []
        self._error = error

    @property
    def source(self) -> ViralSource:
        return self._source

    async def fetch(self, *, limit: int = 100) -> ViralFetchResult:
        return ViralFetchResult(
            source=self._source,
            signals=self._signals,
            error=self._error,
        )


class _StubClassifier(PODReadinessClassifier):
    """Test stub — score = length of phrase clamped 0-100."""

    async def classify(self, phrase: str) -> PODReadinessResult:
        return PODReadinessResult(
            score=min(100, len(phrase)),
            reasoning=f"len={len(phrase)}",
            suggested_styles=["minimal"],
        )

    async def classify_batch(self, phrases: list[str]) -> list[PODReadinessResult]:
        return [await self.classify(p) for p in phrases]


def _sig(source: ViralSource, phrase: str, momentum: int = 30) -> ViralSignal:
    return ViralSignal(
        source=source,
        phrase=phrase,
        detected_at=datetime.now(UTC),
        engagement=100,
        momentum_score=momentum,
        pod_readiness_score=0,
        existing_pod_count=0,
        suggested_styles=[],
    )


@pytest.mark.asyncio
async def test_no_sources_returns_empty() -> None:
    svc = ViralMiningService(sources=[], classifier=_StubClassifier())
    result = await svc.run()
    assert result.signals == []
    assert result.sources_used == []


@pytest.mark.asyncio
async def test_fans_out_and_dedupes() -> None:
    s1 = _sig(ViralSource.REDDIT, "Funny cat memes", momentum=40)
    s2 = _sig(ViralSource.TWITTER, "funny cat memes", momentum=60)   # same phrase, higher momentum
    s3 = _sig(ViralSource.TIKTOK, "vintage motorcycle", momentum=80)

    svc = ViralMiningService(
        sources=[
            _FakeSource(ViralSource.REDDIT, [s1]),
            _FakeSource(ViralSource.TWITTER, [s2]),
            _FakeSource(ViralSource.TIKTOK, [s3]),
        ],
        classifier=_StubClassifier(),
    )
    result = await svc.run(min_pod_readiness=0)

    phrases = {s.phrase.lower() for s in result.signals}
    assert "funny cat memes" in phrases
    assert "vintage motorcycle" in phrases
    assert len(result.signals) == 2  # deduped
    assert set(result.sources_used) >= {"reddit", "twitter", "tiktok"}


@pytest.mark.asyncio
async def test_filters_by_min_pod_readiness() -> None:
    # Stub classifier scores = phrase length. "hi" → 2; "vintage" → 7
    s1 = _sig(ViralSource.REDDIT, "hi")
    s2 = _sig(ViralSource.REDDIT, "a much longer trending phrase")
    svc = ViralMiningService(
        sources=[_FakeSource(ViralSource.REDDIT, [s1, s2])],
        classifier=_StubClassifier(),
    )
    result = await svc.run(min_pod_readiness=20)
    phrases = {s.phrase for s in result.signals}
    assert "a much longer trending phrase" in phrases
    assert "hi" not in phrases


@pytest.mark.asyncio
async def test_skips_classification_when_disabled() -> None:
    s = _sig(ViralSource.REDDIT, "vintage", momentum=50)
    s = s.model_copy(update={"pod_readiness_score": 90})  # pretend already scored
    svc = ViralMiningService(
        sources=[_FakeSource(ViralSource.REDDIT, [s])],
        classifier=_StubClassifier(),
    )
    result = await svc.run(min_pod_readiness=80, classify=False)
    assert len(result.signals) == 1
    assert result.signals[0].pod_readiness_score == 90  # unchanged


@pytest.mark.asyncio
async def test_records_failures() -> None:
    svc = ViralMiningService(
        sources=[
            _FakeSource(ViralSource.REDDIT, [_sig(ViralSource.REDDIT, "ok")]),
            _FakeSource(ViralSource.TIKTOK, error="http_403"),
        ],
        classifier=_StubClassifier(),
    )
    result = await svc.run(min_pod_readiness=0)
    assert "reddit" in result.sources_used
    assert any(src == "tiktok" for src, _ in result.sources_failed)


@pytest.mark.asyncio
async def test_heuristic_classifier_basic() -> None:
    c = HeuristicPODReadinessClassifier()
    out = await c.classify("Funny mom coffee mug")
    # 'mom' and 'coffee' are positive signals → score above default
    assert out.score > 30
    assert "minimal" in out.suggested_styles or "vintage" in out.suggested_styles or "watercolor" in out.suggested_styles
