"""
Trademark risk scoring algorithm.

This is the core intellectual property of Trademark Shield. Pure function —
deterministic, no I/O, fully testable.

## Scoring model

Overall jurisdiction risk score is a weighted combination of 5 factors,
each normalized to 0-100:

| Factor                        | Weight | What it measures                                |
| ----------------------------- | ------ | ----------------------------------------------- |
| active_exact_class            | 40%    | # of active registrations in target Nice class  |
| pending_same_class            | 20%    | # of pending applications (will likely register)|
| active_adjacent_class         | 15%    | # of active registrations in related classes    |
| common_law_density            | 15%    | Unregistered commercial use density             |
| generic_descriptive_inverse   | 10%    | Higher for distinctive phrases, lower for generic|

## Score buckets

| Score   | Level    | Meaning                                       |
| ------- | -------- | --------------------------------------------- |
| 0-20    | Safe     | No known conflicts; proceed                   |
| 21-40   | Low      | Minor flags; review                           |
| 41-60   | Medium   | Notable concerns; consider alternatives       |
| 61-80   | High     | Significant risk; strongly reconsider         |
| 81-100  | Critical | Do not sell; existing trademark is enforced   |
"""

from __future__ import annotations

from dataclasses import dataclass

from scalemyprints.domain.trademark.enums import (
    JurisdictionCode,
    get_adjacent_classes,
    score_to_risk_level,
)
from scalemyprints.domain.trademark.models import (
    JurisdictionRisk,
    TrademarkRecord,
)

# -----------------------------------------------------------------------------
# Scoring weights — central config for tuning
# -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ScoringWeights:
    """
    Percentage weights for each risk factor. Must sum to 100.

    Default values tuned based on POD industry risk patterns:
    - Active exact-class registrations are the primary threat
    - Pending applications are secondary but important
    - Adjacent-class registrations add meaningful but smaller risk
    - Common-law density captures unregistered threats
    - Distinctiveness (inverse of genericness) amplifies the signal
    """

    active_exact_class: int = 40
    pending_same_class: int = 20
    active_adjacent: int = 15
    common_law_density: int = 15
    distinctiveness: int = 10

    def __post_init__(self) -> None:
        total = (
            self.active_exact_class
            + self.pending_same_class
            + self.active_adjacent
            + self.common_law_density
            + self.distinctiveness
        )
        if total != 100:
            raise ValueError(f"Scoring weights must sum to 100, got {total}")


DEFAULT_WEIGHTS = ScoringWeights()


# -----------------------------------------------------------------------------
# The scorer
# -----------------------------------------------------------------------------


class RiskScorer:
    """Pure risk scoring — no I/O, fully deterministic."""

    def __init__(self, weights: ScoringWeights = DEFAULT_WEIGHTS) -> None:
        self._weights = weights

    # --- Per-jurisdiction ---

    def score_jurisdiction(
        self,
        *,
        jurisdiction: JurisdictionCode,
        records: list[TrademarkRecord],
        target_nice_classes: list[int],
        common_law_density: float | None = None,
        phrase_genericness: float = 0.0,
        search_duration_ms: int | None = None,
        search_error: str | None = None,
    ) -> JurisdictionRisk:
        """
        Score risk for a single jurisdiction based on its trademark records.

        Args:
            jurisdiction: The jurisdiction code (US/EU/AU/UK)
            records: Trademark records returned from this jurisdiction
            target_nice_classes: Nice classes the seller intends to sell in
            common_law_density: 0.0-1.0 density of unregistered use
            phrase_genericness: 0.0-1.0 (1.0 = fully generic, low risk)
            search_duration_ms: How long the search took (for diagnostics)
            search_error: Error message if the search failed
        """
        if search_error:
            # Return a "safe" result with the error surfaced — don't falsely
            # report low risk when we actually failed to check
            return JurisdictionRisk(
                code=jurisdiction,
                risk_score=0,
                risk_level=score_to_risk_level(0),
                active_registrations=0,
                pending_applications=0,
                adjacent_class_registrations=0,
                common_law_density=common_law_density,
                arbitrage_available=False,
                matching_records=[],
                search_duration_ms=search_duration_ms,
                error=search_error,
            )

        target_set = set(target_nice_classes)
        adjacent_set = get_adjacent_classes(target_nice_classes)

        # Partition records into buckets
        active_exact: list[TrademarkRecord] = []
        pending_same: list[TrademarkRecord] = []
        active_adjacent: list[TrademarkRecord] = []

        for record in records:
            record_classes = set(record.nice_classes)
            has_exact_overlap = bool(record_classes & target_set)
            has_adjacent_overlap = bool(record_classes & adjacent_set)

            if record.is_active and has_exact_overlap:
                active_exact.append(record)
            elif record.is_pending and has_exact_overlap:
                pending_same.append(record)
            elif record.is_active and has_adjacent_overlap:
                active_adjacent.append(record)

        # Compute component scores (each normalized 0-100)
        active_score = self._score_active_exact(len(active_exact))
        pending_score = self._score_pending(len(pending_same))
        adjacent_score = self._score_adjacent(len(active_adjacent))
        common_law_score = int((common_law_density or 0.0) * 100)
        distinctiveness_score = self._score_distinctiveness(phrase_genericness)

        # Weighted sum
        w = self._weights
        weighted_total = (
            active_score * w.active_exact_class
            + pending_score * w.pending_same_class
            + adjacent_score * w.active_adjacent
            + common_law_score * w.common_law_density
            + distinctiveness_score * w.distinctiveness
        ) / 100

        final_score = max(0, min(100, int(round(weighted_total))))

        return JurisdictionRisk(
            code=jurisdiction,
            risk_score=final_score,
            risk_level=score_to_risk_level(final_score),
            active_registrations=len(active_exact),
            pending_applications=len(pending_same),
            adjacent_class_registrations=len(active_adjacent),
            common_law_density=common_law_density,
            arbitrage_available=final_score < 30,
            matching_records=active_exact + pending_same,
            search_duration_ms=search_duration_ms,
            error=None,
        )

    # --- Overall ---

    def score_overall(
        self,
        *,
        jurisdiction_risks: list[JurisdictionRisk],
        user_selling_in: list[JurisdictionCode],
    ) -> tuple[int, bool]:
        """
        Compute overall risk across jurisdictions.

        Returns:
            (overall_score, had_errors)

        Logic:
        - User can be sued in any jurisdiction they sell in, so we take MAX
        - Jurisdictions with search errors are excluded (can't score what we couldn't check)
        - If all searches errored, overall_score = 0 but had_errors = True
        """
        selling_set = set(user_selling_in)
        relevant = [
            jr for jr in jurisdiction_risks
            if jr.code in selling_set and jr.error is None
        ]

        had_errors = any(
            jr.error is not None
            for jr in jurisdiction_risks
            if jr.code in selling_set
        )

        if not relevant:
            return 0, had_errors

        overall = max(jr.risk_score for jr in relevant)
        return overall, had_errors

    # --- Component score calculators ---

    @staticmethod
    def _score_active_exact(count: int) -> int:
        """
        Active exact-class registrations.

        Each registration adds substantial risk. Saturates at 100.
        """
        if count == 0:
            return 0
        # 1 = 50, 2 = 85, 3+ = 100
        return min(100, 15 + count * 35)

    @staticmethod
    def _score_pending(count: int) -> int:
        """
        Pending applications. Lower weight than active, but still meaningful
        since ~70% of filings eventually register.
        """
        if count == 0:
            return 0
        # 1 = 30, 2 = 55, 3+ = 80
        return min(100, 5 + count * 25)

    @staticmethod
    def _score_adjacent(count: int) -> int:
        """Active registrations in adjacent Nice classes."""
        if count == 0:
            return 0
        # 1 = 25, 2 = 45, 3+ = 65
        return min(100, 5 + count * 20)

    @staticmethod
    def _score_distinctiveness(genericness: float) -> int:
        """
        Distinctiveness = inverse of genericness.

        Generic phrases (high genericness) have LOWER inherent risk because
        they're hard for anyone to monopolize. Distinctive phrases have
        HIGHER inherent risk because they're more likely to be policed.

        Returns: 0-100 where higher = more distinctive = more risk
        """
        genericness = max(0.0, min(1.0, genericness))
        return int((1.0 - genericness) * 100)
