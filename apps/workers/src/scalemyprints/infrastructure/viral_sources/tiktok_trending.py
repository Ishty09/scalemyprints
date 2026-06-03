"""
TikTok trending adapter — scrapes the public Discover page for
trending hashtags.

TikTok doesn't expose a free trending API. We fetch the public
`https://www.tiktok.com/discover` page (or a region-specific variant)
and pull the hashtag titles + view counts from inline JSON.

This is fragile by design (TikTok rotates their schema), so we walk
the JSON tree generically and log when nothing comes back. Adapter
falls back to an empty result on any failure — never raises.
"""

from __future__ import annotations

import json
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


_TT_STATE_RE = re.compile(
    r'<script[^>]+id="SIGI_STATE"[^>]*>(.+?)</script>',
    re.DOTALL,
)
_TT_REHYDRATE_RE = re.compile(
    r'<script[^>]+id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.+?)</script>',
    re.DOTALL,
)


class TikTokTrendingAdapter(ViralSourceAdapter):
    """Scrapes the TikTok Discover page for trending hashtags."""

    @property
    def source(self) -> ViralSource:
        return ViralSource.TIKTOK

    def __init__(
        self,
        *,
        region: str = "US",
        proxy_url: str | None = None,
        timeout_seconds: float = 12.0,
    ) -> None:
        self._region = region
        self._proxy_url = proxy_url
        self._timeout = timeout_seconds

    async def fetch(self, *, limit: int = 50) -> ViralFetchResult:
        start = time.monotonic()
        url = "https://www.tiktok.com/discover"

        try:
            from curl_cffi.requests import AsyncSession  # noqa: PLC0415
        except ImportError:
            return ViralFetchResult(
                source=ViralSource.TIKTOK,
                error="curl_cffi_missing",
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        try:
            async with AsyncSession(
                impersonate="chrome124",
                timeout=self._timeout,
                proxies=(
                    {"https": self._proxy_url, "http": self._proxy_url}
                    if self._proxy_url
                    else None
                ),
            ) as s:
                resp = await s.get(url, headers=rotating_headers())
                if resp.status_code in (403, 429):
                    return ViralFetchResult(
                        source=ViralSource.TIKTOK,
                        error=f"http_{resp.status_code}",
                        duration_ms=int((time.monotonic() - start) * 1000),
                    )
                if resp.status_code >= 400:
                    return ViralFetchResult(
                        source=ViralSource.TIKTOK,
                        error=f"http_{resp.status_code}",
                        duration_ms=int((time.monotonic() - start) * 1000),
                    )
                body = (
                    resp.text
                    if hasattr(resp, "text")
                    else resp.content.decode("utf-8", "ignore")
                )
        except Exception as e:
            logger.warning("tiktok_trending_fetch_failed", error=str(e))
            return ViralFetchResult(
                source=ViralSource.TIKTOK,
                error=f"fetch_failed: {e}",
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        signals = _parse_tiktok(body, limit=limit)
        return ViralFetchResult(
            source=ViralSource.TIKTOK,
            signals=signals,
            duration_ms=int((time.monotonic() - start) * 1000),
        )


def _parse_tiktok(html: str, *, limit: int) -> list[ViralSignal]:
    signals: list[ViralSignal] = []
    now = datetime.now(UTC)

    blob: object | None = None
    for pat in (_TT_REHYDRATE_RE, _TT_STATE_RE):
        m = pat.search(html)
        if m:
            try:
                blob = json.loads(m.group(1))
                break
            except json.JSONDecodeError:
                continue

    if blob is None:
        return signals

    # Walk for any list of {hashtagName, viewCount} or {title, viewCount}
    candidates: list[dict[str, object]] = []

    def _recur(node: object) -> None:
        if isinstance(node, dict):
            keys = set(node.keys())
            if keys & {"hashtagName", "title"} and (
                "viewCount" in keys or "videoCount" in keys or "stats" in keys
            ):
                candidates.append(node)
            for v in node.values():
                _recur(v)
        elif isinstance(node, list):
            for el in node:
                _recur(el)

    _recur(blob)

    for c in candidates[:limit]:
        phrase = c.get("hashtagName") or c.get("title") or ""
        if not isinstance(phrase, str):
            continue
        view_count: int | None = None
        if isinstance(c.get("viewCount"), (int, str)):
            view_count = safe_int(c.get("viewCount"))
        elif isinstance(c.get("videoCount"), (int, str)):
            view_count = safe_int(c.get("videoCount"))
        elif isinstance(c.get("stats"), dict):
            stats = c["stats"]
            if isinstance(stats, dict):
                view_count = safe_int(stats.get("videoCount") or stats.get("viewCount"))

        engagement = view_count or 0
        # Momentum scale: TikTok hashtag view counts can be billions.
        # Use log10 → momentum: 1k=18, 1M=36, 1B=54, 1T=72.
        momentum = 0
        if engagement > 0:
            import math  # noqa: PLC0415

            momentum = min(100, int(math.log10(max(engagement, 1)) * 9))

        try:
            signals.append(
                ViralSignal(
                    source=ViralSource.TIKTOK,
                    phrase=str(phrase)[:400],
                    detected_at=now,
                    engagement=engagement,
                    momentum_score=momentum,
                    pod_readiness_score=0,
                    existing_pod_count=0,
                    suggested_styles=[],
                    note="TikTok Discover",
                )
            )
        except Exception:
            continue

    return signals
