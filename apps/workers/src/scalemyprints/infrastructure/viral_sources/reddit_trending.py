"""
Reddit trending adapter — uses the public RSS feeds for top posts in
POD-relevant subreddits.

Strategy:
- Fetch top-of-day RSS from each subreddit in `subreddits`
- Each post = candidate ViralSignal (phrase = title, engagement = score)
- Reddit's old.reddit.com RSS feed is stable and doesn't require auth

POD-relevant subreddits (default set): r/funny, r/wholesomememes,
r/dankmemes, r/aww, r/teachers, r/nursing, r/dadjokes, r/momlife,
r/wittytshirts, r/petpics.

Adapter NEVER raises. Errors land in `error`.
"""

from __future__ import annotations

import re
import time
from datetime import UTC, datetime
from xml.etree import ElementTree as ET

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.spy.enums import ViralSource
from scalemyprints.domain.spy.models import ViralSignal
from scalemyprints.domain.spy.ports import (
    ViralFetchResult,
    ViralSourceAdapter,
)
from scalemyprints.infrastructure.spy_apis.base import rotating_headers

logger = get_logger(__name__)


DEFAULT_SUBREDDITS = (
    "wholesomememes",
    "dankmemes",
    "funny",
    "AwwwwwLookAtThePuppy",
    "Teachers",
    "nursing",
    "dadjokes",
    "ParentingMemes",
    "wittytshirts",
    "rarepuppers",
)


# Score formatting in Reddit titles like "[Score: 12345]" is rare; we mostly
# parse the <description> CDATA for upvote count when present.
_SCORE_RE = re.compile(r"submitted by.*?\[score[:\s]*(\d[\d,]*)\]", re.IGNORECASE)


class RedditTrendingAdapter(ViralSourceAdapter):
    """Public-RSS reddit trending fetcher. No auth required."""

    @property
    def source(self) -> ViralSource:
        return ViralSource.REDDIT

    def __init__(
        self,
        *,
        subreddits: tuple[str, ...] = DEFAULT_SUBREDDITS,
        per_sub_limit: int = 15,
        timeout_seconds: float = 8.0,
    ) -> None:
        self._subreddits = subreddits
        self._per_sub_limit = per_sub_limit
        self._timeout = timeout_seconds

    async def fetch(self, *, limit: int = 100) -> ViralFetchResult:
        start = time.monotonic()
        try:
            import httpx  # noqa: PLC0415
        except ImportError:
            return ViralFetchResult(
                source=ViralSource.REDDIT,
                error="httpx_missing",
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        signals: list[ViralSignal] = []
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True) as c:
            for sub in self._subreddits:
                if len(signals) >= limit:
                    break
                url = f"https://www.reddit.com/r/{sub}/top/.rss?t=day"
                try:
                    resp = await c.get(url, headers=rotating_headers(accept_html=False))
                    if resp.status_code in (403, 429):
                        logger.info("reddit_trending_blocked", sub=sub, status=resp.status_code)
                        continue
                    if resp.status_code >= 400:
                        continue
                    signals.extend(_parse_rss(resp.text, sub, self._per_sub_limit))
                except Exception as e:
                    logger.warning("reddit_trending_fetch_failed", sub=sub, error=str(e))
                    continue

        return ViralFetchResult(
            source=ViralSource.REDDIT,
            signals=signals[:limit],
            duration_ms=int((time.monotonic() - start) * 1000),
        )


# -----------------------------------------------------------------------------
# Parser
# -----------------------------------------------------------------------------


_ATOM_NS = "{http://www.w3.org/2005/Atom}"


def _parse_rss(xml: str, sub: str, limit: int) -> list[ViralSignal]:
    signals: list[ViralSignal] = []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return signals

    now = datetime.now(UTC)
    for entry in root.findall(f"{_ATOM_NS}entry")[:limit]:
        title_el = entry.find(f"{_ATOM_NS}title")
        title = (title_el.text or "").strip() if title_el is not None else ""
        if not title or len(title) < 3:
            continue
        # Pull link
        link_url: str | None = None
        link_el = entry.find(f"{_ATOM_NS}link")
        if link_el is not None:
            link_url = link_el.attrib.get("href")

        # Try to extract score from <content>
        engagement = 0
        content_el = entry.find(f"{_ATOM_NS}content")
        if content_el is not None and content_el.text:
            m = _SCORE_RE.search(content_el.text)
            if m:
                try:
                    engagement = int(m.group(1).replace(",", ""))
                except ValueError:
                    engagement = 0

        # Momentum: rough proxy — Reddit top-of-day posts rank by upvotes
        # over 24h. We clip score 0-3000 → 0-100.
        momentum = min(100, int(engagement / 30)) if engagement else 0

        try:
            signals.append(
                ViralSignal(
                    source=ViralSource.REDDIT,
                    source_url=link_url,  # type: ignore[arg-type]
                    phrase=title[:400],
                    detected_at=now,
                    engagement=engagement,
                    momentum_score=momentum,
                    pod_readiness_score=0,  # filled in by PODReadinessClassifier
                    existing_pod_count=0,
                    suggested_styles=[],
                    note=f"r/{sub}",
                )
            )
        except Exception:
            continue

    return signals
