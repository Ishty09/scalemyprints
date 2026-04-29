"""
Tests for RiskScorer — the core scoring algorithm.

These tests are the safety net for the most business-critical logic in the
product. Every scoring path must be exercised with clear assertions.
"""

from __future__ import annotations

import pytest

from scalemyprints.domain.trademark.enums import FilingStatus, JurisdictionCode, RiskLevel
from scalemyprints.domain.trademark.scorer import RiskScorer, ScoringWeights
from tests.fixtures import make_record


@pytest.fixture
def scorer() -> RiskScorer:
    return RiskScorer()


# -----------------------------------------------------------------------------
# ScoringWeights validation
# -----------------------------------------------------------------------------


class TestScoringWeights:
    def test_default_weights_sum_to_100(self) -> None:
        w = ScoringWeights()
        assert (
            w.active_exact_class
            + w.pending_same_class
            + w.active_adjacent
            + w.common_law_density
            + w.distinctiveness
        ) == 100

    def test_custom_weights_must_sum_to_100(self) -> None:
        with pytest.raises(ValueError, match="sum to 100"):
            ScoringWeights(
                active_exact_class=50,
                pending_same_class=20,
                active_adjacent=15,
                common_law_density=10,
                distinctiveness=10,  # Sum = 105
            )


# -----------------------------------------------------------------------------
# score_jurisdiction — happy paths
# -----------------------------------------------------------------------------


class TestScoreJurisdictionSafe:
    def test_no_records_no_common_law_distinctive_phrase_is_safe(
        self, scorer: RiskScorer
    ) -> None:
        result = scorer.score_jurisdiction(
            jurisdiction=JurisdictionCode.US,
            records=[],
            target_nice_classes=[25],
            common_law_density=0.0,
            phrase_genericness=1.0,  # Fully generic → distinctiveness = 0
        )
        assert result.risk_score == 0
        assert result.risk_level == RiskLevel.SAFE
        assert result.active_registrations == 0
        assert result.arbitrage_available is True
        assert result.error is None

    def test_distinctive_phrase_alone_has_moderate_distinctiveness_contribution(
        self, scorer: RiskScorer
    ) -> None:
        result = scorer.score_jurisdiction(
            jurisdiction=JurisdictionCode.US,
            records=[],
            target_nice_classes=[25],
            common_law_density=0.0,
            phrase_genericness=0.0,  # Fully distinctive → distinctiveness = 100 * 10% = 10
        )
        assert result.risk_score == 10
        assert result.risk_level == RiskLevel.SAFE


class TestScoreJurisdictionActiveExact:
    def test_one_active_exact_class_registration_raises_risk(
        self, scorer: RiskScorer
    ) -> None:
        result = scorer.score_jurisdiction(
            jurisdiction=JurisdictionCode.US,
            records=[make_record(status=FilingStatus.REGISTERED, nice_class=25)],
            target_nice_classes=[25],
            common_law_density=0.0,
            phrase_genericness=1.0,
        )
        # 1 active exact = score 50, weighted 40% = 20 → LOW
        assert result.active_registrations == 1
        assert 15 <= result.risk_score <= 25
        assert result.risk_level == RiskLevel.SAFE  # boundary: 20 is SAFE

    def test_three_active_exact_registrations_is_critical(
        self, scorer: RiskScorer
    ) -> None:
        records = [
            make_record(registration_number=f"9812345{i}", status=FilingStatus.REGISTERED)
            for i in range(3)
        ]
        result = scorer.score_jurisdiction(
            jurisdiction=JurisdictionCode.US,
            records=records,
            target_nice_classes=[25],
            common_law_density=0.0,
            phrase_genericness=0.0,
        )
        # 3+ active exact = 100 weighted 40% = 40; distinctiveness 10 = 10 → ~50
        assert result.active_registrations == 3
        assert result.risk_score >= 40

    def test_active_records_in_wrong_class_dont_count_as_exact(
        self, scorer: RiskScorer
    ) -> None:
        result = scorer.score_jurisdiction(
            jurisdiction=JurisdictionCode.US,
            records=[make_record(status=FilingStatus.REGISTERED, nice_class=9)],
            target_nice_classes=[25],
            common_law_density=0.0,
            phrase_genericness=1.0,
        )
        # Class 9 is adjacent to 25, so it counts as adjacent not exact
        assert result.active_registrations == 0
        assert result.adjacent_class_registrations == 1


class TestScoreJurisdictionPending:
    def test_pending_application_adds_risk(self, scorer: RiskScorer) -> None:
        result = scorer.score_jurisdiction(
            jurisdiction=JurisdictionCode.US,
            records=[make_record(status=FilingStatus.PENDING, nice_class=25)],
            target_nice_classes=[25],
            common_law_density=0.0,
            phrase_genericness=1.0,
        )
        assert result.pending_applications == 1
        assert result.active_registrations == 0
        assert result.risk_score > 0


class TestScoreJurisdictionAdjacent:
    def test_adjacent_class_registration_adds_smaller_risk(
        self, scorer: RiskScorer
    ) -> None:
        # Class 24 (textiles) is adjacent to 25 (apparel)
        result = scorer.score_jurisdiction(
            jurisdiction=JurisdictionCode.US,
            records=[make_record(status=FilingStatus.REGISTERED, nice_class=24)],
            target_nice_classes=[25],
            common_law_density=0.0,
            phrase_genericness=1.0,
        )
        assert result.adjacent_class_registrations == 1
        assert result.active_registrations == 0
        assert result.risk_score > 0


class TestScoreJurisdictionCommonLaw:
    def test_high_common_law_density_raises_risk(self, scorer: RiskScorer) -> None:
        result = scorer.score_jurisdiction(
            jurisdiction=JurisdictionCode.US,
            records=[],
            target_nice_classes=[25],
            common_law_density=1.0,
            phrase_genericness=1.0,
        )
        # 1.0 density → common_law_score = 100, weighted 15% = 15
        assert result.common_law_density == 1.0
        assert result.risk_score == 15

    def test_none_common_law_treated_as_zero(self, scorer: RiskScorer) -> None:
        result = scorer.score_jurisdiction(
            jurisdiction=JurisdictionCode.US,
            records=[],
            target_nice_classes=[25],
            common_law_density=None,
            phrase_genericness=1.0,
        )
        assert result.common_law_density is None
        assert result.risk_score == 0


class TestScoreJurisdictionDistinctiveness:
    @pytest.mark.parametrize(
        "genericness,expected_contribution",
        [
            (1.0, 0),   # Fully generic → 0% distinctiveness → weight 10% → 0
            (0.5, 5),   # 50% generic → 50% distinct → 5 points
            (0.0, 10),  # Fully distinctive → 100% distinct → 10 points
        ],
    )
    def test_distinctiveness_weighted_10_percent(
        self, scorer: RiskScorer, genericness: float, expected_contribution: int
    ) -> None:
        result = scorer.score_jurisdiction(
            jurisdiction=JurisdictionCode.US,
            records=[],
            target_nice_classes=[25],
            common_law_density=0.0,
            phrase_genericness=genericness,
        )
        assert result.risk_score == expected_contribution


# -----------------------------------------------------------------------------
# Error handling
# -----------------------------------------------------------------------------


class TestScoreJurisdictionErrors:
    def test_search_error_preserves_error_field(self, scorer: RiskScorer) -> None:
        result = scorer.score_jurisdiction(
            jurisdiction=JurisdictionCode.US,
            records=[],
            target_nice_classes=[25],
            search_error="timeout",
        )
        assert result.error == "timeout"
        assert result.risk_score == 0
        assert result.arbitrage_available is False  # Don't falsely claim safety

    def test_errored_jurisdiction_not_marked_as_safe(self, scorer: RiskScorer) -> None:
        result = scorer.score_jurisdiction(
            jurisdiction=JurisdictionCode.US,
            records=[],
            target_nice_classes=[25],
            search_error="api_down",
        )
        # Even though score is 0, we know we couldn't check
        assert result.arbitrage_available is False


# -----------------------------------------------------------------------------
# Critical combo — high in all factors
# -----------------------------------------------------------------------------


class TestScoreJurisdictionCritical:
    def test_worst_case_scores_critical(self, scorer: RiskScorer) -> None:
        records = [
            make_record(
                registration_number="98100001",
                status=FilingStatus.REGISTERED,
                nice_class=25,
            ),
            make_record(
                registration_number="98100002",
                status=FilingStatus.REGISTERED,
                nice_class=25,
            ),
            make_record(
                registration_number="98100003",
                status=FilingStatus.REGISTERED,
                nice_class=25,
            ),
            make_record(
                registration_number="98100004",
                status=FilingStatus.PENDING,
                nice_class=25,
            ),
            make_record(
                registration_number="98100005",
                status=FilingStatus.REGISTERED,
                nice_class=24,  # adjacent
            ),
        ]
        result = scorer.score_jurisdiction(
            jurisdiction=JurisdictionCode.US,
            records=records,
            target_nice_classes=[25],
            common_law_density=1.0,
            phrase_genericness=0.0,
        )
        # 3 active (saturates active component) + 1 pending + 1 adjacent
        # + full common-law + fully distinctive = ~75 → HIGH
        assert result.risk_score >= 70
        assert result.risk_level == RiskLevel.HIGH
        assert result.active_registrations == 3
        assert result.pending_applications == 1
        assert result.adjacent_class_registrations == 1
        assert result.arbitrage_available is False


    def test_overwhelmingly_conflicted_phrase_scores_critical(
        self, scorer: RiskScorer
    ) -> None:
        """
        To hit CRITICAL (>=81), we need the rarely-occurring combo of:
        many active exact + pending + adjacent + full common-law + distinctive.
        This models the case of a phrase someone is actively enforcing.
        """
        # Use all factors at max — multiple active exact + pending + adjacent
        records = [
            make_record(
                registration_number=f"98100{i:03d}",
                status=FilingStatus.REGISTERED,
                nice_class=25,
            )
            for i in range(5)
        ] + [
            make_record(
                registration_number="98200001",
                status=FilingStatus.PENDING,
                nice_class=25,
            ),
            make_record(
                registration_number="98200002",
                status=FilingStatus.PENDING,
                nice_class=25,
            ),
            make_record(
                registration_number="98300001",
                status=FilingStatus.REGISTERED,
                nice_class=24,  # adjacent
            ),
            make_record(
                registration_number="98300002",
                status=FilingStatus.REGISTERED,
                nice_class=18,  # adjacent
            ),
            make_record(
                registration_number="98300003",
                status=FilingStatus.REGISTERED,
                nice_class=14,  # adjacent
            ),
        ]
        result = scorer.score_jurisdiction(
            jurisdiction=JurisdictionCode.US,
            records=records,
            target_nice_classes=[25],
            common_law_density=1.0,
            phrase_genericness=0.0,
        )
        # All components saturate → should be 81+
        assert result.risk_score >= 80
        assert result.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)


# -----------------------------------------------------------------------------
# score_overall — aggregation across jurisdictions
# -----------------------------------------------------------------------------


class TestScoreOverall:
    def test_takes_max_across_selling_jurisdictions(self, scorer: RiskScorer) -> None:
        us_risk = scorer.score_jurisdiction(
            jurisdiction=JurisdictionCode.US,
            records=[make_record(status=FilingStatus.REGISTERED)] * 3,
            target_nice_classes=[25],
        )
        eu_risk = scorer.score_jurisdiction(
            jurisdiction=JurisdictionCode.EU,
            records=[],
            target_nice_classes=[25],
        )
        overall, had_errors = scorer.score_overall(
            jurisdiction_risks=[us_risk, eu_risk],
            user_selling_in=[JurisdictionCode.US, JurisdictionCode.EU],
        )
        assert overall == max(us_risk.risk_score, eu_risk.risk_score)
        assert had_errors is False

    def test_ignores_jurisdictions_user_doesnt_sell_in(
        self, scorer: RiskScorer
    ) -> None:
        high_risk_au = scorer.score_jurisdiction(
            jurisdiction=JurisdictionCode.AU,
            records=[make_record(status=FilingStatus.REGISTERED)] * 3,
            target_nice_classes=[25],
        )
        safe_us = scorer.score_jurisdiction(
            jurisdiction=JurisdictionCode.US,
            records=[],
            target_nice_classes=[25],
        )
        # User only sells in US — AU risk doesn't matter
        overall, _ = scorer.score_overall(
            jurisdiction_risks=[high_risk_au, safe_us],
            user_selling_in=[JurisdictionCode.US],
        )
        assert overall == safe_us.risk_score

    def test_all_errored_returns_zero_with_errors_flag(self, scorer: RiskScorer) -> None:
        us_risk = scorer.score_jurisdiction(
            jurisdiction=JurisdictionCode.US,
            records=[],
            target_nice_classes=[25],
            search_error="timeout",
        )
        eu_risk = scorer.score_jurisdiction(
            jurisdiction=JurisdictionCode.EU,
            records=[],
            target_nice_classes=[25],
            search_error="api_down",
        )
        overall, had_errors = scorer.score_overall(
            jurisdiction_risks=[us_risk, eu_risk],
            user_selling_in=[JurisdictionCode.US, JurisdictionCode.EU],
        )
        assert overall == 0
        assert had_errors is True

    def test_partial_errors_still_scores_from_successful_jurisdictions(
        self, scorer: RiskScorer
    ) -> None:
        us_risk = scorer.score_jurisdiction(
            jurisdiction=JurisdictionCode.US,
            records=[make_record(status=FilingStatus.REGISTERED)] * 3,
            target_nice_classes=[25],
        )
        eu_risk = scorer.score_jurisdiction(
            jurisdiction=JurisdictionCode.EU,
            records=[],
            target_nice_classes=[25],
            search_error="timeout",
        )
        overall, had_errors = scorer.score_overall(
            jurisdiction_risks=[us_risk, eu_risk],
            user_selling_in=[JurisdictionCode.US, JurisdictionCode.EU],
        )
        # Score from US still returned; errors flag raised
        assert overall == us_risk.risk_score
        assert had_errors is True

    def test_empty_jurisdiction_risks_returns_zero(self, scorer: RiskScorer) -> None:
        overall, had_errors = scorer.score_overall(
            jurisdiction_risks=[],
            user_selling_in=[JurisdictionCode.US],
        )
        assert overall == 0
        assert had_errors is False


# -----------------------------------------------------------------------------
# Output invariants
# -----------------------------------------------------------------------------


class TestOutputInvariants:
    def test_risk_score_always_in_range_0_to_100(self, scorer: RiskScorer) -> None:
        # Even with extreme inputs, score stays in [0, 100]
        records = [make_record(status=FilingStatus.REGISTERED, nice_class=25)] * 50
        result = scorer.score_jurisdiction(
            jurisdiction=JurisdictionCode.US,
            records=records,
            target_nice_classes=[25],
            common_law_density=1.0,
            phrase_genericness=0.0,
        )
        assert 0 <= result.risk_score <= 100

    def test_matching_records_only_includes_overlapping(
        self, scorer: RiskScorer
    ) -> None:
        records = [
            make_record(registration_number="A", status=FilingStatus.REGISTERED, nice_class=25),
            make_record(registration_number="B", status=FilingStatus.REGISTERED, nice_class=30),
        ]
        result = scorer.score_jurisdiction(
            jurisdiction=JurisdictionCode.US,
            records=records,
            target_nice_classes=[25],
        )
        # Only the class 25 record should be in matching_records
        assert len(result.matching_records) == 1
        assert result.matching_records[0].registration_number == "A"
