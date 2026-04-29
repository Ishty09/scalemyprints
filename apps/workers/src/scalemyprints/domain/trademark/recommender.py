"""
Recommendation generator.

Turns raw risk analysis into actionable, human-readable recommendations.
Pure rules-based logic — deterministic, no LLM calls.

Design:
- Generate all applicable recommendations; let the UI/caller filter or rank
- Each recommendation has a severity and optional action
- Phrasing is kind but direct — users need to make a business decision
"""

from __future__ import annotations

from scalemyprints.domain.trademark.enums import JurisdictionCode, RecommendationSeverity
from scalemyprints.domain.trademark.models import (
    JurisdictionRisk,
    TrademarkRecommendation,
)


class RecommendationGenerator:
    """Generate actionable recommendations from jurisdiction-level risk data."""

    def generate(
        self,
        *,
        jurisdiction_risks: list[JurisdictionRisk],
        user_selling_in: list[JurisdictionCode],
    ) -> list[TrademarkRecommendation]:
        """
        Generate all applicable recommendations, ordered by severity.

        Output is a flat list; UI can group or highlight as needed.
        """
        selling_set = set(user_selling_in)
        recommendations: list[TrademarkRecommendation] = []

        # Errors first — they block other recommendations from being trusted
        for jr in jurisdiction_risks:
            if jr.error and jr.code in selling_set:
                recommendations.append(
                    TrademarkRecommendation(
                        severity=RecommendationSeverity.WARNING,
                        message=(
                            f"We couldn't fully check {jr.code} "
                            "(the trademark office didn't respond)."
                        ),
                        action="Try again in a few minutes, or search directly on the office site.",
                    )
                )

        # Critical blockers — score 70+ is a clear do-not-proceed signal
        for jr in jurisdiction_risks:
            if jr.code in selling_set and jr.risk_score >= 70:
                recommendations.append(
                    TrademarkRecommendation(
                        severity=RecommendationSeverity.DANGER,
                        message=(
                            f"{jr.code}: High/Critical risk — "
                            f"{jr.active_registrations} active registration(s) match."
                        ),
                        action=f"Do NOT sell this phrase in {jr.code}.",
                    )
                )

        # Elevated risk
        elevated_markets = [
            jr for jr in jurisdiction_risks
            if jr.code in selling_set and 50 <= jr.risk_score < 70
        ]
        for jr in elevated_markets:
            recommendations.append(
                TrademarkRecommendation(
                    severity=RecommendationSeverity.WARNING,
                    message=(
                        f"{jr.code}: Elevated risk — {jr.active_registrations} active "
                        f"registration(s) overlap your target class."
                    ),
                    action="Strongly consider a different phrase or restrict to safer markets.",
                )
            )

        # Arbitrage opportunities
        safe_codes = [
            jr.code for jr in jurisdiction_risks
            if jr.code in selling_set and jr.risk_score < 30 and jr.error is None
        ]
        risky_codes = [
            jr.code for jr in jurisdiction_risks
            if jr.code in selling_set and jr.risk_score >= 60
        ]
        if safe_codes and risky_codes:
            recommendations.append(
                TrademarkRecommendation(
                    severity=RecommendationSeverity.INFO,
                    message=(
                        f"Safer in {', '.join(safe_codes)} than in "
                        f"{', '.join(risky_codes)}."
                    ),
                    action=(
                        f"Consider restricting your listings to "
                        f"{', '.join(safe_codes)} only."
                    ),
                )
            )

        # Pending applications — future threats
        for jr in jurisdiction_risks:
            if jr.code in selling_set and jr.pending_applications > 0:
                recommendations.append(
                    TrademarkRecommendation(
                        severity=RecommendationSeverity.INFO,
                        message=(
                            f"{jr.code}: {jr.pending_applications} pending "
                            f"application(s) found."
                        ),
                        action=(
                            "These typically register in 6-18 months. "
                            "Monitor this phrase to catch new filings."
                        ),
                    )
                )

        # Adjacent-class warnings
        for jr in jurisdiction_risks:
            if (
                jr.code in selling_set
                and jr.adjacent_class_registrations > 0
                and jr.risk_score < 60
            ):
                recommendations.append(
                    TrademarkRecommendation(
                        severity=RecommendationSeverity.INFO,
                        message=(
                            f"{jr.code}: {jr.adjacent_class_registrations} active "
                            f"registration(s) in related product categories."
                        ),
                        action=(
                            "Lower direct risk, but owners of related-category marks "
                            "sometimes expand or enforce across categories."
                        ),
                    )
                )

        # All-clear message
        all_safe = all(
            jr.risk_score < 20 and jr.error is None
            for jr in jurisdiction_risks
            if jr.code in selling_set
        )
        if all_safe and jurisdiction_risks:
            recommendations.append(
                TrademarkRecommendation(
                    severity=RecommendationSeverity.SUCCESS,
                    message="All clear across your target jurisdictions.",
                    action=(
                        "No known conflicts. As always, monitor ongoing — new "
                        "filings can change this at any time."
                    ),
                )
            )

        return recommendations
