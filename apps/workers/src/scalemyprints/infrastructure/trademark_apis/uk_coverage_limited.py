"""
Stub UK trademark adapter — returns a coverage-limited error immediately.

Used when no residential proxy is configured. Both UKIPO and TMView block
datacenter IPs (Cloudflare WAF and Akamai bot detection respectively), so
free server-side queries are impossible. Set UK_PROXY_URL to enable the
real chain.
"""

from __future__ import annotations

from scalemyprints.domain.trademark.enums import JurisdictionCode
from scalemyprints.domain.trademark.ports import TrademarkSearchResult


class UKCoverageLimitedAdapter:
    """Returns coverage_limited error without making any network calls."""

    jurisdiction: JurisdictionCode = JurisdictionCode.UK

    async def search(
        self, phrase: str, nice_classes: list[int]
    ) -> TrademarkSearchResult:
        del phrase, nice_classes  # unused
        return TrademarkSearchResult(
            jurisdiction=self.jurisdiction,
            records=[],
            duration_ms=0,
            error="coverage_limited",
        )

    async def aclose(self) -> None:
        return None
