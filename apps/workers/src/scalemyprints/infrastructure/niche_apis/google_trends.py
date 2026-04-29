"""
Google Trends adapter — free public data via pytrends.

pytrends is an unofficial library that scrapes trends.google.com.
No API key required. Trade-offs:
- Sometimes rate-limited (429) → graceful degrade
- Returns 0-100 normalized "interest" index, not raw search volumes
- Country-specific via geo parameter (US, GB, AU, CA, DE)
- 90-day window default; we use 90d and compute growth_pct from start vs end

Returns TrendsData (never raises) — failures populate `error`.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.niche.enums import Country
from scalemyprints.domain.niche.ports import TrendsData

logger = get_logger(__name__)


# Country → Google Trends geo code
_GEO_MAP: dict[Country, str] = {
    Country.US: "US",
    Country.UK: "GB",  # Google uses GB, not UK
    Country.AU: "AU",
    Country.CA: "CA",
    Country.DE: "DE",
}


class GoogleTrendsAdapter:
    """Free Google Trends adapter via pytrends. Sync library wrapped in thread."""

    def __init__(
        self,
        *,
        timeframe: str = "today 3-m",  # last 90 days
        request_timeout_seconds: int = 10,
    ) -> None:
        self._timeframe = timeframe
        self._timeout = request_timeout_seconds

    async def fetch(self, keyword: str, country: Country) -> TrendsData:
        """
        Fetch trend data for keyword in country.

        Runs the sync pytrends call in a thread to avoid blocking.
        """
        start = time.monotonic()
        log = logger.bind(service="google_trends", keyword=keyword, country=country.value)

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(self._fetch_sync, keyword, country),
                timeout=self._timeout,
            )
            duration_ms = int((time.monotonic() - start) * 1000)
            log.info(
                "trends_fetch_complete",
                volume_index=result["volume_index"],
                growth_pct=result["growth_pct"],
                duration_ms=duration_ms,
            )
            return TrendsData(
                search_volume_index=result["volume_index"],
                growth_pct_90d=result["growth_pct"],
                related_queries=result["related"],
                sample_points=result["sample_points"],
                duration_ms=duration_ms,
                error=None,
            )
        except asyncio.TimeoutError:
            duration_ms = int((time.monotonic() - start) * 1000)
            log.warning("trends_timeout", duration_ms=duration_ms)
            return TrendsData(
                search_volume_index=0,
                duration_ms=duration_ms,
                error="timeout",
            )
        except Exception as e:  # noqa: BLE001
            duration_ms = int((time.monotonic() - start) * 1000)
            log.warning("trends_error", error=str(e)[:120], duration_ms=duration_ms)
            return TrendsData(
                search_volume_index=0,
                duration_ms=duration_ms,
                error=f"unexpected:{e.__class__.__name__}",
            )

    def _fetch_sync(self, keyword: str, country: Country) -> dict[str, Any]:
        """
        Sync pytrends call. Imports inline so the library is optional —
        absence shouldn't crash imports of this module.
        """
        try:
            from pytrends.request import TrendReq  # type: ignore[import-not-found]
        except ImportError as e:
            raise RuntimeError(
                "pytrends not installed; run: pip install pytrends"
            ) from e

        geo = _GEO_MAP.get(country, "US")
        pytrends = TrendReq(hl="en-US", tz=0, timeout=(5, 10))
        pytrends.build_payload([keyword], cat=0, timeframe=self._timeframe, geo=geo)

        # Interest over time → DataFrame
        df = pytrends.interest_over_time()
        if df is None or df.empty:
            return {
                "volume_index": 0,
                "growth_pct": None,
                "related": [],
                "sample_points": 0,
            }

        values = df[keyword].tolist()
        sample_points = len(values)

        # Mean of last 7 entries as "current" volume index
        recent = values[-7:] if len(values) >= 7 else values
        volume_index = int(round(sum(recent) / len(recent)))

        # Growth % = (last_quarter_avg - first_quarter_avg) / first_quarter_avg * 100
        growth_pct = None
        if sample_points >= 6:
            quarter = max(1, sample_points // 4)
            first_avg = sum(values[:quarter]) / quarter
            last_avg = sum(values[-quarter:]) / quarter
            if first_avg > 0:
                growth_pct = round(((last_avg - first_avg) / first_avg) * 100, 1)

        # Related queries (best effort — may fail with 429/CAPTCHA)
        related: list[str] = []
        try:
            rq = pytrends.related_queries()
            top_df = rq.get(keyword, {}).get("top")
            if top_df is not None and not top_df.empty:
                related = top_df["query"].head(10).tolist()
        except Exception:  # noqa: BLE001
            pass  # related queries optional

        return {
            "volume_index": max(0, min(100, volume_index)),
            "growth_pct": growth_pct,
            "related": related,
            "sample_points": sample_points,
        }
