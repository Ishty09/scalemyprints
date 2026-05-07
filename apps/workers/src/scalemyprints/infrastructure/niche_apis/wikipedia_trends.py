"""
Wikipedia Pageviews-based trends adapter — free, unlimited, no auth.

Why Wikipedia?
- Wikipedia Pageviews API is one of the very few public free APIs that
  serves datacenter IPs without rate limiting or anti-bot challenges.
- Daily pageview counts on a topic correlate well with public interest
  for any niche big enough to have a Wikipedia article.
- Returns ~100% reliability vs pytrends (Google Trends) which 429s
  immediately on datacenter IPs.

Mapping Wikipedia signals → TrendsData:
- volume_index (0-100): log-scaled daily pageview avg.
  Reference: 10 views/day → 0, 1k/day → 50, 100k+/day → 100.
- growth_pct_90d: ratio of last-30-day avg vs first-30-day avg.
- related_queries: alternate titles returned by Wikipedia OpenSearch
  for the same query (semantically similar topics).

Limitations:
- Wikipedia covers established topics, not micro-niches like
  "dog mom shirt". For free-text marketing keywords, we tokenize the
  phrase and search for any token that has a Wikipedia article. If
  none, the result is `error="no_wikipedia_article"`.
- Wikipedia views are global, not country-segmented. Country param
  is currently ignored (only English Wikipedia queried).
"""

from __future__ import annotations

import math
import time
from datetime import date, timedelta
from types import TracebackType
from typing import Any

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.niche.enums import Country
from scalemyprints.domain.niche.ports import TrendsData
from scalemyprints.infrastructure.trademark_apis.base import HttpClientFactory

logger = get_logger(__name__)


WIKIPEDIA_API_BASE = "https://en.wikipedia.org"
PAGEVIEWS_API_BASE = "https://wikimedia.org"

# Pageview anchors for the log-volume mapping (calibrated by hand on a
# spread of POD-relevant topics):
#   "Dog"           → ~3500 views/day   → ~75
#   "Print on demand" → ~360/day        → ~50
#   "Pickleball"    → ~1500/day         → ~65
_VOLUME_LOG_MIN = 1.0   # log10(10) — floor
_VOLUME_LOG_MAX = 5.0   # log10(100k) — ceiling

# Words too generic to be useful Wikipedia article matches
_STOP_TOKENS: frozenset[str] = frozenset({
    "the", "and", "for", "with", "your", "our", "from",
    "shirt", "tee", "tshirt", "t-shirt", "hoodie", "mug", "sticker",
    "design", "designs", "gift", "gifts", "lover", "lovers",
})


class WikipediaTrendsAdapter:
    """Free Wikipedia-pageviews-based trends signal."""

    def __init__(
        self,
        *,
        http_factory: HttpClientFactory | None = None,
        request_timeout_seconds: float = 10.0,
    ) -> None:
        factory = http_factory or HttpClientFactory()
        self._search_client = factory.build(
            base_url=WIKIPEDIA_API_BASE,
            headers={
                "Accept": "application/json",
                "Api-User-Agent": "ScaleMyPrints/0.1 (https://scalemyprints.com; hello@scalemyprints.com)",
            },
        )
        self._pageviews_client = factory.build(
            base_url=PAGEVIEWS_API_BASE,
            headers={
                "Accept": "application/json",
                "Api-User-Agent": "ScaleMyPrints/0.1 (https://scalemyprints.com; hello@scalemyprints.com)",
            },
        )
        self._timeout = request_timeout_seconds

    async def __aenter__(self) -> "WikipediaTrendsAdapter":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._search_client.aclose()
        await self._pageviews_client.aclose()

    async def fetch(self, keyword: str, country: Country) -> TrendsData:
        del country  # English Wikipedia covers all English-speaking markets
        start = time.monotonic()
        log = logger.bind(service="wikipedia_trends", keyword=keyword)

        try:
            article, related = await self._find_best_article(keyword)
            if not article:
                duration_ms = int((time.monotonic() - start) * 1000)
                log.info("wikipedia_no_article_match", duration_ms=duration_ms)
                return TrendsData(
                    search_volume_index=0,
                    duration_ms=duration_ms,
                    error="no_wikipedia_article",
                )

            views = await self._fetch_pageviews(article)
            duration_ms = int((time.monotonic() - start) * 1000)

            if not views:
                log.info(
                    "wikipedia_no_views_data",
                    article=article,
                    duration_ms=duration_ms,
                )
                return TrendsData(
                    search_volume_index=0,
                    related_queries=related,
                    duration_ms=duration_ms,
                    error="no_pageviews_data",
                )

            stats = _compute_stats(views)
            log.info(
                "wikipedia_trends_complete",
                article=article,
                volume_index=stats["volume_index"],
                growth_pct=stats["growth_pct"],
                sample_points=stats["sample_points"],
                duration_ms=duration_ms,
            )

            return TrendsData(
                search_volume_index=stats["volume_index"],
                growth_pct_90d=stats["growth_pct"],
                related_queries=related,
                sample_points=stats["sample_points"],
                duration_ms=duration_ms,
                error=None,
            )

        except Exception as e:  # noqa: BLE001
            duration_ms = int((time.monotonic() - start) * 1000)
            log.warning(
                "wikipedia_trends_error",
                error=str(e)[:120],
                duration_ms=duration_ms,
            )
            return TrendsData(
                search_volume_index=0,
                duration_ms=duration_ms,
                error=f"unexpected:{e.__class__.__name__}",
            )

    # ------------------------------------------------------------------
    # Wikipedia OpenSearch — find the best matching article
    # ------------------------------------------------------------------

    async def _find_best_article(self, keyword: str) -> tuple[str | None, list[str]]:
        """
        Return (top_article_title, related_titles).

        Strategy: full-phrase OpenSearch first; if no match, fall back to
        the most distinctive single token. POD-style keywords like
        "dog mom shirt" rarely match as a phrase but "dog" or "mom" do.
        """
        # 1. Try the full phrase
        results = await self._opensearch(keyword, limit=5)
        if results:
            top = results[0]
            related = results[1:]
            return top, related

        # 2. Tokenize and try the most distinctive token
        tokens = [
            t for t in keyword.lower().split()
            if len(t) >= 3 and t not in _STOP_TOKENS
        ]
        for token in tokens:
            results = await self._opensearch(token, limit=5)
            if results:
                return results[0], results[1:]

        return None, []

    async def _opensearch(self, query: str, *, limit: int = 5) -> list[str]:
        """Wikipedia OpenSearch — returns up to `limit` matching article titles."""
        params = {
            "action": "opensearch",
            "search": query,
            "limit": str(limit),
            "namespace": "0",
            "format": "json",
        }
        try:
            response = await self._search_client.get(
                "/w/api.php", params=params, timeout=self._timeout,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("wikipedia_opensearch_error", error=str(e)[:120])
            return []

        if response.status_code != 200:
            return []

        try:
            data = response.json()
        except ValueError:
            return []

        # OpenSearch returns: [query, [titles], [descriptions], [urls]]
        if not isinstance(data, list) or len(data) < 2:
            return []
        titles = data[1]
        if not isinstance(titles, list):
            return []
        return [str(t) for t in titles if isinstance(t, str)]

    # ------------------------------------------------------------------
    # Wikipedia Pageviews API — daily counts for an article
    # ------------------------------------------------------------------

    async def _fetch_pageviews(self, article: str) -> list[int]:
        """Return list of daily pageview counts (last 90 days)."""
        end_date = date.today() - timedelta(days=2)  # API has ~24-48h lag
        start_date = end_date - timedelta(days=90)
        title = article.replace(" ", "_")

        path = (
            f"/api/rest_v1/metrics/pageviews/per-article/"
            f"en.wikipedia/all-access/all-agents/{title}/daily/"
            f"{start_date.strftime('%Y%m%d')}/{end_date.strftime('%Y%m%d')}"
        )
        try:
            response = await self._pageviews_client.get(
                path, timeout=self._timeout,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "wikipedia_pageviews_error",
                article=article,
                error=str(e)[:120],
            )
            return []

        if response.status_code == 404:
            return []
        if response.status_code != 200:
            return []

        try:
            data = response.json()
        except ValueError:
            return []

        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            return []

        return [
            int(it.get("views", 0))
            for it in items
            if isinstance(it, dict) and isinstance(it.get("views"), int)
        ]


# -----------------------------------------------------------------------------
# Pure helpers
# -----------------------------------------------------------------------------


def _compute_stats(views: list[int]) -> dict[str, Any]:
    """Compute volume index, growth %, and sample-point count from daily views."""
    sample_points = len(views)
    if not views:
        return {"volume_index": 0, "growth_pct": None, "sample_points": 0}

    # Volume: log-scale the average daily views
    avg = sum(views) / len(views)
    if avg <= 0:
        volume_index = 0
    else:
        log_v = math.log10(avg)
        scaled = (log_v - _VOLUME_LOG_MIN) / (_VOLUME_LOG_MAX - _VOLUME_LOG_MIN)
        volume_index = int(round(max(0.0, min(1.0, scaled)) * 100))

    # Growth: last-30 vs first-30 average
    growth_pct: float | None = None
    if sample_points >= 30:
        first_30 = views[:30]
        last_30 = views[-30:]
        first_avg = sum(first_30) / 30
        last_avg = sum(last_30) / 30
        if first_avg > 0:
            growth_pct = round(((last_avg - first_avg) / first_avg) * 100, 1)

    return {
        "volume_index": volume_index,
        "growth_pct": growth_pct,
        "sample_points": sample_points,
    }
