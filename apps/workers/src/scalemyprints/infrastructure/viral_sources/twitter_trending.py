"""
Twitter / X trending adapter — pulls the public trending widget JSON.

Background: X's official Trends API requires paid access. We use the
public `https://trends24.in/{country}/` aggregator which scrapes X's
own trending widget and republishes it as plain HTML. It's free,
unauthenticated, and stable.

Each row = a trending phrase. We approximate engagement from the
"X tweets" counter Trends24 shows next to each entry.
"""

from __future__ import annotations

import re
import time
from datetime import UTC, datetime

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.spy.enums import ViralSource
from scalemyprints.domain.spy.models import ViralSignal
from scalemyprints.domain.spy.ports import (
    ViralFetchResult,
    ViralSourceAdapter,
)
from scalemyprints.infrastructure.spy_apis.base import (
    rotating_headers,
    safe_int,
)

logger = get_logger(__name__)


# Each card on trends24 looks like
#   <li><a href="...">Trump</a> <span class="tweet-count">421K</span></li>
_TREND_CARD_RE = re.compile(
    r"<li[^>]*>\s*<a[^>]+>(?P<phrase>[^<]+)</a>"
    r"(?:.*?<span[^>]+class=\"tweet-count\"[^>]*>(?P<count>[^<]+)</span>)?",
    re.DOTALL,
)


class TwitterTrendingAdapter(ViralSourceAdapter):
    """Public trends24.in HTML scraping. No auth."""

    @property
    def source(self) -> ViralSource:
        return ViralSource.TWITTER

    def __init__(
        self,
        *,
        region_slug: str = "united-states",
        timeout_seconds: float = 8.0,
    ) -> None:
        self._region = region_slug
        self._timeout = timeout_seconds

    async def fetch(self, *, limit: int = 50) -> ViralFetchResult:
        start = time.monotonic()
        url = f"https://trends24.in/{self._region}/"

        try:
            import httpx  # noqa: PLC0415
        except ImportError:
            return ViralFetchResult(
                source=ViralSource.TWITTER,
                error="httpx_missing",
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, follow_redirects=True
            ) as c:
                resp = await c.get(url, headers=rotating_headers())
                if resp.status_code in (403, 429):
                    return ViralFetchResult(
                        source=ViralSource.TWITTER,
                        error=f"http_{resp.status_code}",
                        duration_ms=int((time.monotonic() - start) * 1000),
                    )
                resp.raise_for_status()
                html = resp.text
        except Exception as e:
            logger.warning("twitter_trending_fetch_failed", error=str(e))
            return ViralFetchResult(
                source=ViralSource.TWITTER,
                error=f"fetch_failed: {e}",
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        signals = _parse_trends24(html, limit=limit)
        return ViralFetchResult(
            source=ViralSource.TWITTER,
            signals=signals,
            duration_ms=int((time.monotonic() - start) * 1000),
        )


def _parse_trends24(html: str, *, limit: int) -> list[ViralSignal]:
    signals: list[ViralSignal] = []
    seen: set[str] = set()
    now = datetime.now(UTC)

    for m in _TREND_CARD_RE.finditer(html):
        phrase = m.group("phrase").strip()
        if not phrase or phrase in seen or len(phrase) < 2:
            continue
        seen.add(phrase)
        raw_count = (m.group("count") or "").strip()
        engagement = _parse_short_number(raw_count)
        momentum = _engagement_to_momentum(engagement)

        try:
            signals.append(
                ViralSignal(
                    source=ViralSource.TWITTER,
                    phrase=phrase[:400],
                    detected_at=now,
                    engagement=engagement,
                    momentum_score=momentum,
                    pod_readiness_score=0,
                    existing_pod_count=0,
                    suggested_styles=[],
                    note="X / Twitter trends24",
                )
            )
        except Exception:
            continue

        if len(signals) >= limit:
            break

    return signals


def _parse_short_number(raw: str) -> int:
    """Parse counts like '421K', '1.2M', '3.4B' → integer."""
    if not raw:
        return 0
    raw = raw.replace(",", "").strip()
    m = re.match(r"^([\d.]+)\s*([KMBT]?)$", raw, re.IGNORECASE)
    if not m:
        return safe_int(raw) or 0
    base = float(m.group(1))
    mult = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000, "T": 1_000_000_000_000}
    return int(base * mult.get(m.group(2).upper(), 1))


def _engagement_to_momentum(engagement: int) -> int:
    if engagement <= 0:
        return 0
    import math  # noqa: PLC0415

    # 1k → 18, 100k → 50, 1M → 60, 10M → 70, 100M → 80
    return min(100, int(math.log10(max(engagement, 1)) * 10))
