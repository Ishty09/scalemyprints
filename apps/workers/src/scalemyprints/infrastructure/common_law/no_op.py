"""
No-op CommonLawChecker.

Phase A default. Always returns 0.0 density — effectively removes the
common-law factor from risk scoring until we have a real implementation
in Phase B (Etsy/Google Shopping search).

Using this (rather than None) keeps the search service code simple —
it always has a checker to call.
"""

from __future__ import annotations

from scalemyprints.core.logging import get_logger

logger = get_logger(__name__)


class NoOpCommonLawChecker:
    """Always returns 0.0 — disables common-law signal cleanly."""

    async def estimate_density(self, phrase: str) -> float:
        logger.debug("common_law_noop", phrase=phrase)
        return 0.0
