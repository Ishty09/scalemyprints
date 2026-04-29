"""Tests for RecommendationGenerator."""

from __future__ import annotations

import pytest

from scalemyprints.domain.trademark.enums import (
    FilingStatus,
    JurisdictionCode,
    RecommendationSeverity,
)
from scalemyprints.domain.trademark.recommender import RecommendationGenerator
from scalemyprints.domain.trademark.scorer import RiskScorer
from tests.fixtures import make_record


@pytest.fixture
def generator() -> RecommendationGenerator:
    return RecommendationGenerator()


@pytest.fixture
def scorer() -> RiskScorer:
    return RiskScorer()


class TestRecommendationGenerator:
    def test_all_safe_produces_success_message(
        self, generator: RecommendationGenerator, scorer: RiskScorer
    ) -> None:
        us_risk = scorer.score_jurisdiction(
            jurisdiction=JurisdictionCode.US, records=[], target_nice_classes=[25]
        )
        eu_risk = scorer.score_jurisdiction(
            jurisdiction=JurisdictionCode.EU, records=[], target_nice_classes=[25]
        )
        recs = generator.generate(
            jurisdiction_risks=[us_risk, eu_risk],
            user_selling_in=[JurisdictionCode.US, JurisdictionCode.EU],
        )
        severities = [r.severity for r in recs]
        assert RecommendationSeverity.SUCCESS in severities

    def test_high_risk_produces_danger_recommendation(
        self, generator: RecommendationGenerator, scorer: RiskScorer
    ) -> None:
        # 3 active + 1 pending + 1 adjacent + common law + distinctive = ~75
        records = [
            make_record(
                registration_number=f"98100{i:03d}",
                status=FilingStatus.REGISTERED,
                nice_class=25,
            )
            for i in range(3)
        ] + [
            make_record(
                registration_number="98200001",
                status=FilingStatus.PENDING,
                nice_class=25,
            ),
            make_record(
                registration_number="98300001",
                status=FilingStatus.REGISTERED,
                nice_class=24,
            ),
        ]
        us_risk = scorer.score_jurisdiction(
            jurisdiction=JurisdictionCode.US,
            records=records,
            target_nice_classes=[25],
            common_law_density=1.0,
            phrase_genericness=0.0,
        )
        assert us_risk.risk_score >= 70  # Score should cross DANGER threshold
        recs = generator.generate(
            jurisdiction_risks=[us_risk],
            user_selling_in=[JurisdictionCode.US],
        )
        severities = [r.severity for r in recs]
        assert RecommendationSeverity.DANGER in severities

    def test_arbitrage_opportunity_surfaced(
        self, generator: RecommendationGenerator, scorer: RiskScorer
    ) -> None:
        safe_us = scorer.score_jurisdiction(
            jurisdiction=JurisdictionCode.US,
            records=[],
            target_nice_classes=[25],
        )
        risky_eu = scorer.score_jurisdiction(
            jurisdiction=JurisdictionCode.EU,
            records=[make_record(status=FilingStatus.REGISTERED)] * 3,
            target_nice_classes=[25],
            common_law_density=1.0,
            phrase_genericness=0.0,
        )
        recs = generator.generate(
            jurisdiction_risks=[safe_us, risky_eu],
            user_selling_in=[JurisdictionCode.US, JurisdictionCode.EU],
        )
        messages = " ".join(r.message for r in recs)
        # An info-level message suggesting safer markets
        assert "safer" in messages.lower() or "restrict" in messages.lower()

    def test_pending_applications_noted(
        self, generator: RecommendationGenerator, scorer: RiskScorer
    ) -> None:
        us_risk = scorer.score_jurisdiction(
            jurisdiction=JurisdictionCode.US,
            records=[make_record(status=FilingStatus.PENDING, nice_class=25)],
            target_nice_classes=[25],
        )
        recs = generator.generate(
            jurisdiction_risks=[us_risk],
            user_selling_in=[JurisdictionCode.US],
        )
        messages = " ".join(r.message for r in recs).lower()
        assert "pending" in messages

    def test_search_error_produces_warning(
        self, generator: RecommendationGenerator, scorer: RiskScorer
    ) -> None:
        errored = scorer.score_jurisdiction(
            jurisdiction=JurisdictionCode.US,
            records=[],
            target_nice_classes=[25],
            search_error="timeout",
        )
        recs = generator.generate(
            jurisdiction_risks=[errored],
            user_selling_in=[JurisdictionCode.US],
        )
        severities = [r.severity for r in recs]
        assert RecommendationSeverity.WARNING in severities

    def test_empty_jurisdictions_returns_empty_list(
        self, generator: RecommendationGenerator
    ) -> None:
        recs = generator.generate(
            jurisdiction_risks=[],
            user_selling_in=[JurisdictionCode.US],
        )
        assert recs == []

    def test_ignores_jurisdictions_user_doesnt_sell_in(
        self, generator: RecommendationGenerator, scorer: RiskScorer
    ) -> None:
        risky_au = scorer.score_jurisdiction(
            jurisdiction=JurisdictionCode.AU,
            records=[make_record(status=FilingStatus.REGISTERED)] * 3,
            target_nice_classes=[25],
            common_law_density=1.0,
            phrase_genericness=0.0,
        )
        recs = generator.generate(
            jurisdiction_risks=[risky_au],
            user_selling_in=[JurisdictionCode.US],  # Not AU
        )
        # No danger rec because user doesn't sell in AU
        severities = [r.severity for r in recs]
        assert RecommendationSeverity.DANGER not in severities
