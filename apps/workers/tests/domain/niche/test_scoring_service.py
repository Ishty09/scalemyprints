"""Tests for niche scoring service — sub-score builders."""

from __future__ import annotations

from datetime import date

import pytest

from scalemyprints.domain.niche.enums import (
    CompetitionLevel,
    NicheHealth,
    TrendDirection,
)
from scalemyprints.domain.niche.scoring_service import (
    ScoringWeights,
    build_competition_score,
    build_demand_score,
    build_profitability_score,
    build_seasonality_score,
    build_trend_score,
    calculate_nhs,
)


# -----------------------------------------------------------------------------
# ScoringWeights validation
# -----------------------------------------------------------------------------


class TestScoringWeights:
    def test_default_weights_sum_to_1(self):
        w = ScoringWeights()
        total = w.demand + w.trend + w.competition + w.profitability + w.seasonality
        assert abs(total - 1.0) < 0.001

    def test_invalid_weights_raise(self):
        with pytest.raises(ValueError, match="sum to 1.0"):
            ScoringWeights(demand=0.5, trend=0.5, competition=0.5,
                           profitability=0.5, seasonality=0.5)

    def test_custom_weights_accepted(self):
        w = ScoringWeights(
            demand=0.4, trend=0.3, competition=0.1,
            profitability=0.15, seasonality=0.05,
        )
        assert w.demand == 0.4


# -----------------------------------------------------------------------------
# Demand score
# -----------------------------------------------------------------------------


class TestDemandScore:
    def test_pure_search_volume(self):
        signal = build_demand_score(
            search_volume_index=70, listing_count=None, source="google_trends"
        )
        assert signal.score == 70
        assert signal.listing_count is None

    def test_search_volume_clamped_to_100(self):
        signal = build_demand_score(
            search_volume_index=150, listing_count=None, source="google_trends"
        )
        assert signal.score == 100

    def test_search_volume_clamped_to_0(self):
        signal = build_demand_score(
            search_volume_index=-50, listing_count=None, source="google_trends"
        )
        assert signal.score == 0

    def test_listing_count_blends_in(self):
        # 70 trends × 0.7 + 25 listing × 0.3 = 49 + 7.5 = 56
        signal = build_demand_score(
            search_volume_index=70, listing_count=100, source="google_trends"
        )
        assert 50 <= signal.score <= 60

    def test_listing_count_capped_at_1000(self):
        signal_500 = build_demand_score(
            search_volume_index=50, listing_count=500, source="x"
        )
        signal_5000 = build_demand_score(
            search_volume_index=50, listing_count=5000, source="x"
        )
        # 5000 listings shouldn't dramatically beat 500 (capped)
        assert signal_5000.score - signal_500.score < 15

    def test_zero_listings_uses_volume_only(self):
        signal = build_demand_score(
            search_volume_index=60, listing_count=0, source="x"
        )
        assert signal.score == 60


# -----------------------------------------------------------------------------
# Trend score
# -----------------------------------------------------------------------------


class TestTrendScore:
    def test_strong_growth_rising(self):
        signal = build_trend_score(growth_pct_90d=60.0, sample_points=12)
        assert signal.direction == TrendDirection.RISING
        assert signal.score >= 90

    def test_moderate_growth_rising(self):
        signal = build_trend_score(growth_pct_90d=25.0, sample_points=12)
        assert signal.direction == TrendDirection.RISING
        assert 65 <= signal.score <= 85

    def test_stable_zero_growth(self):
        signal = build_trend_score(growth_pct_90d=0.0, sample_points=12)
        assert signal.direction == TrendDirection.STABLE
        assert 45 <= signal.score <= 55

    def test_declining(self):
        signal = build_trend_score(growth_pct_90d=-25.0, sample_points=12)
        assert signal.direction == TrendDirection.DECLINING
        assert 15 <= signal.score <= 35

    def test_collapsing(self):
        signal = build_trend_score(growth_pct_90d=-80.0, sample_points=12)
        assert signal.direction == TrendDirection.DECLINING
        assert signal.score <= 10

    def test_insufficient_data_returns_neutral(self):
        signal = build_trend_score(growth_pct_90d=100.0, sample_points=2)
        assert signal.direction == TrendDirection.STABLE
        assert signal.score == 50

    def test_none_growth_returns_neutral(self):
        signal = build_trend_score(growth_pct_90d=None, sample_points=10)
        assert signal.score == 50

    def test_score_clamped_0_100(self):
        signal_high = build_trend_score(growth_pct_90d=500.0, sample_points=12)
        signal_low = build_trend_score(growth_pct_90d=-500.0, sample_points=12)
        assert 0 <= signal_high.score <= 100
        assert 0 <= signal_low.score <= 100


# -----------------------------------------------------------------------------
# Competition score (inverted — higher = less competition)
# -----------------------------------------------------------------------------


class TestCompetitionScore:
    def test_low_competition_high_score(self):
        signal = build_competition_score(
            listing_count=50, unique_sellers_estimate=50, avg_listing_age_days=100.0
        )
        assert signal.level == CompetitionLevel.LOW
        assert signal.score >= 85

    def test_medium_competition(self):
        signal = build_competition_score(
            listing_count=500, unique_sellers_estimate=375, avg_listing_age_days=180.0
        )
        assert signal.level == CompetitionLevel.MEDIUM

    def test_high_competition(self):
        signal = build_competition_score(
            listing_count=5000, unique_sellers_estimate=2500, avg_listing_age_days=200.0
        )
        assert signal.level == CompetitionLevel.HIGH
        assert signal.score < 50

    def test_saturated(self):
        signal = build_competition_score(
            listing_count=20000, unique_sellers_estimate=10000, avg_listing_age_days=300.0
        )
        assert signal.level == CompetitionLevel.SATURATED
        assert signal.score < 25

    def test_unknown_listings_neutral(self):
        signal = build_competition_score(
            listing_count=None, unique_sellers_estimate=None, avg_listing_age_days=None
        )
        assert signal.score == 50
        assert signal.level == CompetitionLevel.MEDIUM

    def test_high_seller_diversity_bonus(self):
        # 80% unique sellers should bump score
        signal_with_diversity = build_competition_score(
            listing_count=500, unique_sellers_estimate=400, avg_listing_age_days=100.0
        )
        signal_no_diversity = build_competition_score(
            listing_count=500, unique_sellers_estimate=100, avg_listing_age_days=100.0
        )
        assert signal_with_diversity.score >= signal_no_diversity.score

    def test_old_listings_bonus(self):
        signal_old = build_competition_score(
            listing_count=500, unique_sellers_estimate=300, avg_listing_age_days=400.0
        )
        signal_new = build_competition_score(
            listing_count=500, unique_sellers_estimate=300, avg_listing_age_days=30.0
        )
        assert signal_old.score >= signal_new.score


# -----------------------------------------------------------------------------
# Profitability score
# -----------------------------------------------------------------------------


class TestProfitabilityScore:
    def test_high_margin(self):
        # $35 - 20% fees - $8 production = $20 margin
        signal = build_profitability_score(avg_price_usd=35.0, sample_size=10)
        assert signal.score >= 80

    def test_decent_margin(self):
        # $24.99 - 20% fees - $8 = $11.99
        signal = build_profitability_score(avg_price_usd=24.99, sample_size=10)
        assert 50 <= signal.score <= 80

    def test_thin_margin(self):
        # $14 - 20% fees - $8 = $3.20
        signal = build_profitability_score(avg_price_usd=14.0, sample_size=10)
        assert 20 <= signal.score <= 50

    def test_loss(self):
        # $9 - 20% fees - $8 = -$0.80
        signal = build_profitability_score(avg_price_usd=9.0, sample_size=10)
        assert signal.score <= 5
        assert signal.estimated_margin_usd is not None
        assert signal.estimated_margin_usd < 0

    def test_no_data_neutral(self):
        signal = build_profitability_score(avg_price_usd=None, sample_size=0)
        assert signal.score == 50
        assert signal.estimated_margin_usd is None

    def test_zero_sample_neutral(self):
        signal = build_profitability_score(avg_price_usd=20.0, sample_size=0)
        assert signal.score == 50


# -----------------------------------------------------------------------------
# Seasonality score
# -----------------------------------------------------------------------------


class TestSeasonalityScore:
    def test_imminent_event_high_score(self):
        signal = build_seasonality_score(
            nearest_event_name="Christmas",
            nearest_event_date=date(2026, 12, 25),
            nearest_event_pod_relevance=100,
            as_of=date(2026, 12, 22),
        )
        assert signal.score >= 90
        assert signal.days_until_event == 3

    def test_30_days_out_strong(self):
        signal = build_seasonality_score(
            nearest_event_name="Mother's Day",
            nearest_event_date=date(2026, 5, 10),
            nearest_event_pod_relevance=100,
            as_of=date(2026, 4, 27),
        )
        assert 65 <= signal.score <= 100
        assert signal.days_until_event == 13

    def test_60_days_out_moderate(self):
        signal = build_seasonality_score(
            nearest_event_name="Christmas",
            nearest_event_date=date(2026, 12, 25),
            nearest_event_pod_relevance=100,
            as_of=date(2026, 10, 26),
        )
        assert 40 <= signal.score <= 70

    def test_far_future_low_score(self):
        signal = build_seasonality_score(
            nearest_event_name="Christmas",
            nearest_event_date=date(2026, 12, 25),
            nearest_event_pod_relevance=100,
            as_of=date(2026, 4, 27),
        )
        assert signal.score <= 25

    def test_no_event_baseline(self):
        signal = build_seasonality_score(
            nearest_event_name=None,
            nearest_event_date=None,
            nearest_event_pod_relevance=None,
            as_of=date(2026, 4, 27),
        )
        assert signal.score == 30  # baseline for evergreen niches
        assert signal.days_until_event is None

    def test_low_relevance_event_scaled_down(self):
        # Event in 3 days but only 30% POD relevant
        signal_low = build_seasonality_score(
            nearest_event_name="Civic Holiday",
            nearest_event_date=date(2026, 4, 30),
            nearest_event_pod_relevance=30,
            as_of=date(2026, 4, 27),
        )
        signal_high = build_seasonality_score(
            nearest_event_name="Christmas",
            nearest_event_date=date(2026, 4, 30),
            nearest_event_pod_relevance=100,
            as_of=date(2026, 4, 27),
        )
        assert signal_low.score < signal_high.score

    def test_past_event_rolls_to_next_year(self):
        # Event was yesterday — should treat as ~365 days away
        signal = build_seasonality_score(
            nearest_event_name="St. Patricks Day",
            nearest_event_date=date(2026, 3, 17),
            nearest_event_pod_relevance=80,
            as_of=date(2026, 3, 18),
        )
        # Should NOT crash, should treat as next year
        assert signal.score >= 0
        assert signal.days_until_event is not None


# -----------------------------------------------------------------------------
# Top-level NHS calculator
# -----------------------------------------------------------------------------


class TestCalculateNHS:
    def test_perfect_niche_hot(
        self,
        sample_demand_high,
        sample_trend_rising,
        sample_competition_low,
        sample_profitability_good,
        sample_seasonality_close,
    ):
        nhs, health = calculate_nhs(
            demand=sample_demand_high,
            trend=sample_trend_rising,
            competition=sample_competition_low,
            profitability=sample_profitability_good,
            seasonality=sample_seasonality_close,
        )
        assert nhs >= 70
        assert health in (NicheHealth.HOT, NicheHealth.PROMISING)

    def test_health_thresholds(
        self,
        sample_demand_high,
        sample_trend_rising,
        sample_competition_low,
        sample_profitability_good,
        sample_seasonality_close,
    ):
        # High = HOT
        nhs, health = calculate_nhs(
            demand=sample_demand_high,
            trend=sample_trend_rising,
            competition=sample_competition_low,
            profitability=sample_profitability_good,
            seasonality=sample_seasonality_close,
        )
        if nhs >= 75:
            assert health == NicheHealth.HOT
        elif nhs >= 55:
            assert health == NicheHealth.PROMISING

    def test_score_clamped_to_100(
        self,
        sample_demand_high,
        sample_trend_rising,
        sample_competition_low,
        sample_profitability_good,
        sample_seasonality_close,
    ):
        nhs, _ = calculate_nhs(
            demand=sample_demand_high,
            trend=sample_trend_rising,
            competition=sample_competition_low,
            profitability=sample_profitability_good,
            seasonality=sample_seasonality_close,
        )
        assert 0 <= nhs <= 100

    def test_custom_weights(
        self,
        sample_demand_high,
        sample_trend_rising,
        sample_competition_low,
        sample_profitability_good,
        sample_seasonality_close,
    ):
        # Heavy weight on demand
        weights_demand_heavy = ScoringWeights(
            demand=0.7, trend=0.1, competition=0.05,
            profitability=0.1, seasonality=0.05,
        )
        nhs_heavy, _ = calculate_nhs(
            demand=sample_demand_high,
            trend=sample_trend_rising,
            competition=sample_competition_low,
            profitability=sample_profitability_good,
            seasonality=sample_seasonality_close,
            weights=weights_demand_heavy,
        )
        # With demand-heavy weights, score should approximate demand more
        assert abs(nhs_heavy - sample_demand_high.score) < 20
