"""
Facebook (Meta) Ad Library adapter.

Public Ad Library URL pattern:
  https://www.facebook.com/ads/library/?active_status=all
    &ad_type=all
    &q=<keyword>
    &country=ALL
    &media_type=all

Meta exposes a GraphQL endpoint for the political-ad slice with an
official API key. For *commercial* ads, the library is browser-only —
we scrape the public HTML with curl_cffi + chrome impersonation. JSON
payloads come back inline as `<script>` snippets.

The adapter NEVER raises — it returns a result with `error` set when
the page is blocked or the parser fails.

Optional: if FB_AD_LIBRARY_TOKEN is configured, we additionally hit the
official Marketing API for the political slice. Most POD ads aren't
political so it's complementary.
"""

from __future__ import annotations

import json
import re
import time
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.spy.ad_library_models import AdPlatform, AdSpyHit
from scalemyprints.infrastructure.spy_apis.base import rotating_headers

logger = get_logger(__name__)


class AdLibraryResult(BaseModel):
    """Adapter return type — never raises."""

    model_config = ConfigDict(frozen=True)

    platform: AdPlatform
    hits: list[AdSpyHit] = Field(default_factory=list)
    duration_ms: int = 0
    error: str | None = None


@runtime_checkable
class AdLibraryAdapter(Protocol):
    """All ad libraries implement this surface."""

    @property
    def platform(self) -> AdPlatform: ...

    async def search(
        self,
        *,
        keyword: str | None = None,
        page_handle: str | None = None,
        country: str = "ALL",
        limit: int = 25,
    ) -> AdLibraryResult: ...


class FacebookAdLibraryAdapter(AdLibraryAdapter):
    """Public-page scraping path. Doesn't need a Meta access token."""

    @property
    def platform(self) -> AdPlatform:
        return AdPlatform.FACEBOOK

    def __init__(
        self,
        *,
        proxy_url: str | None = None,
        timeout_seconds: float = 12.0,
    ) -> None:
        self._proxy_url = proxy_url
        self._timeout = timeout_seconds

    async def search(
        self,
        *,
        keyword: str | None = None,
        page_handle: str | None = None,
        country: str = "ALL",
        limit: int = 25,
    ) -> AdLibraryResult:
        start = time.monotonic()
        if not keyword and not page_handle:
            return AdLibraryResult(
                platform=AdPlatform.FACEBOOK,
                error="empty_query",
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        params = [
            "active_status=all",
            "ad_type=all",
            f"country={country}",
            "media_type=all",
        ]
        if keyword:
            params.append(f"q={quote(keyword)}")
        if page_handle:
            params.append(f"view_all_page_id={quote(page_handle)}")

        url = "https://www.facebook.com/ads/library/?" + "&".join(params)
        html, err = await self._fetch(url)
        if err:
            return AdLibraryResult(
                platform=AdPlatform.FACEBOOK,
                error=err,
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        hits = _parse_fb_ads(html, limit=limit, page_handle=page_handle)
        return AdLibraryResult(
            platform=AdPlatform.FACEBOOK,
            hits=hits,
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    async def _fetch(self, url: str) -> tuple[str, str | None]:
        try:
            from curl_cffi.requests import AsyncSession  # noqa: PLC0415
        except ImportError:
            import httpx  # noqa: PLC0415

            try:
                async with httpx.AsyncClient(
                    timeout=self._timeout, follow_redirects=True
                ) as c:
                    resp = await c.get(url, headers=rotating_headers())
                    if resp.status_code in (403, 429):
                        return "", f"http_{resp.status_code}"
                    resp.raise_for_status()
                    return resp.text, None
            except Exception as e:
                return "", f"httpx_failed: {e}"

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
                resp = await s.get(url, headers=rotating_headers(), allow_redirects=True)
                if resp.status_code in (403, 429):
                    return "", f"http_{resp.status_code}"
                if resp.status_code >= 400:
                    return "", f"http_{resp.status_code}"
                body = (
                    resp.text
                    if hasattr(resp, "text")
                    else resp.content.decode("utf-8", "ignore")
                )
                return body, None
        except Exception as e:
            logger.warning("fb_ad_library_fetch_failed", url=url, error=str(e))
            return "", f"fetch_failed: {e}"


# -----------------------------------------------------------------------------
# Parser
# -----------------------------------------------------------------------------


# Facebook embeds the ad-library results inside scripts of the form:
#   require("ScheduledServerJS").handle(...);
#   {"__bbox":{"complete":true,"result":{"data":{"ad_library_main":{"search_results":...}}}}
# We pull all JSON blobs from those scripts and walk for the right key.

_BBOX_RE = re.compile(r'\{"__bbox":\{.+?"complete":true.+?\}\}', re.DOTALL)


def _parse_fb_ads(
    html: str,
    *,
    limit: int,
    page_handle: str | None,
) -> list[AdSpyHit]:
    hits: list[AdSpyHit] = []
    seen_ids: set[str] = set()

    for raw in _BBOX_RE.findall(html):
        try:
            blob = json.loads(raw)
        except json.JSONDecodeError:
            continue

        for ad in _walk_for_ads(blob):
            if not isinstance(ad, dict):
                continue
            ad_id = str(ad.get("ad_archive_id") or ad.get("ad_id") or "").strip()
            if not ad_id or ad_id in seen_ids:
                continue
            seen_ids.add(ad_id)

            page_name = ad.get("page_name") or page_handle or ""
            snapshot = ad.get("snapshot") or {}
            body_txt: str | None = None
            if isinstance(snapshot, dict):
                body = snapshot.get("body")
                if isinstance(body, dict):
                    body_txt = body.get("text") or body.get("markup")
                elif isinstance(body, str):
                    body_txt = body

            started_ms = ad.get("start_date")
            ended_ms = ad.get("end_date")
            try:
                started = (
                    datetime.fromtimestamp(int(started_ms), tz=UTC)
                    if started_ms
                    else None
                )
            except Exception:
                started = None
            try:
                last_seen = (
                    datetime.fromtimestamp(int(ended_ms), tz=UTC)
                    if ended_ms
                    else None
                )
            except Exception:
                last_seen = None

            countries = ad.get("countries") or []
            if isinstance(countries, str):
                countries = [countries]

            try:
                hits.append(
                    AdSpyHit(
                        platform=AdPlatform.FACEBOOK,
                        ad_id=ad_id,
                        page_or_handle=str(page_name)[:200] or ad_id,
                        page_id=str(ad.get("page_id")) if ad.get("page_id") else None,
                        primary_text=(
                            str(body_txt)[:2000] if isinstance(body_txt, str) else None
                        ),
                        cta=(
                            str(snapshot.get("cta_text"))[:80]
                            if isinstance(snapshot.get("cta_text"), str)
                            else None
                        ),
                        landing_url=(
                            snapshot.get("link_url")
                            if isinstance(snapshot.get("link_url"), str)
                            else None
                        ),
                        started_at=started,
                        last_seen_at=last_seen,
                        impressions_lower=ad.get("impressions_with_index", {}).get(
                            "impressions_lower"
                        )
                        if isinstance(ad.get("impressions_with_index"), dict)
                        else None,
                        impressions_upper=ad.get("impressions_with_index", {}).get(
                            "impressions_upper"
                        )
                        if isinstance(ad.get("impressions_with_index"), dict)
                        else None,
                        countries=[str(c) for c in countries if isinstance(c, str)][:20],
                    )
                )
            except Exception:
                continue

            if len(hits) >= limit:
                return hits

    return hits


def _walk_for_ads(node: object) -> list[dict[str, object]]:
    """DFS for any list under an `ad_library_main` / `edges` / `result` key."""
    found: list[dict[str, object]] = []

    def _recur(n: object) -> None:
        if isinstance(n, dict):
            for k, v in n.items():
                # Heuristic: lists named like search_results, edges, ads, results
                if k in ("search_results", "edges", "ads", "results") and isinstance(
                    v, list
                ):
                    for el in v:
                        # GraphQL nodes wrap inside {"node": {...}}
                        if isinstance(el, dict) and "node" in el and isinstance(el["node"], dict):
                            found.append(el["node"])
                        elif isinstance(el, dict):
                            found.append(el)
                else:
                    _recur(v)
        elif isinstance(n, list):
            for el in n:
                _recur(el)

    _recur(node)
    return found
