"""
Marker API adapter — 3rd-party US trademark data.

Used as the **default** US trademark search provider since it requires no
USPTO API key (which has a multi-day approval process). When the user
later obtains a USPTO key, the Container can switch to USPTOClient.

Marker API:
- Aggregates USPTO public trademark data
- Free tier: 1000 lookups/month, no key required
- Endpoint: https://markerapi.com/api/v2/trademarks/...
- Returns JSON

Limitations:
- ~24h delay vs USPTO live data
- Free tier rate-limited (about 30/min)
- Some advanced filters not available

Implements TrademarkAPI protocol — drop-in replacement for USPTOClient.
"""

from __future__ import annotations

import asyncio
from types import TracebackType
from typing import Any
from urllib.parse import quote_plus

import httpx

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.trademark.enums import ACTIVE_STATUSES, FilingStatus, JurisdictionCode
from scalemyprints.domain.trademark.models import TrademarkRecord
from scalemyprints.domain.trademark.ports import TrademarkSearchResult
from scalemyprints.infrastructure.trademark_apis.base import (
    HttpClientFactory,
    measure_duration,
    run_with_retry,
)
from scalemyprints.infrastructure.trademark_apis.normalizers import (
    normalize_date_string,
    normalize_filing_status,
    parse_nice_classes,
)

logger = get_logger(__name__)

MARKER_DEFAULT_BASE_URL = "https://markerapi.com"
# Path template — Marker uses /api/v2/trademarks/trademark/{phrase}/start/{n}/username/{u}/password/{p}
# For free tier without auth: /api/v2/trademarks/trademark/{phrase}
MARKER_SEARCH_PATH_TEMPLATE = "/api/v2/trademarks/trademark/{phrase}/start/1"
MAX_RESULTS = 50

USPTO_TSDR_URL_TEMPLATE = (
    "https://tsdr.uspto.gov/#caseNumber={sn}&caseType=DEFAULT&searchType=statusSearch"
)


class MarkerAPIClient:
    """
    US trademark search via Marker API (3rd-party USPTO data aggregator).

    Acts as our default US TrademarkAPI implementation when no USPTO key is
    configured. Same interface as USPTOClient — fully interchangeable.
    """

    jurisdiction: JurisdictionCode = JurisdictionCode.US

    def __init__(
        self,
        *,
        base_url: str = MARKER_DEFAULT_BASE_URL,
        username: str | None = None,
        password: str | None = None,
        http_factory: HttpClientFactory | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password

        if client is not None:
            self._client = client
            self._owns_client = False
        else:
            factory = http_factory or HttpClientFactory()
            self._client = factory.build(base_url=self._base_url)
            self._owns_client = True

    async def __aenter__(self) -> "MarkerAPIClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Public API (TrademarkAPI protocol)
    # ------------------------------------------------------------------

    async def search(
        self, phrase: str, nice_classes: list[int]
    ) -> TrademarkSearchResult:
        """
        Search Marker API for a phrase, then filter results by Nice class.

        Marker doesn't accept a class filter parameter, so we get all
        matches and post-filter client-side. Acceptable for our query
        volume; would not scale to 1000s of results per phrase.
        """
        log = logger.bind(service="marker", phrase=phrase, nice_classes=nice_classes)

        async with measure_duration() as elapsed:
            try:
                records = await self._search_once(phrase)
                # Post-filter by Nice class (or include if class data missing)
                filtered = _filter_by_classes(records, nice_classes)

                log.info("marker_search_complete", count=len(filtered), duration_ms=elapsed())
                return TrademarkSearchResult(
                    jurisdiction=self.jurisdiction,
                    records=filtered,
                    duration_ms=elapsed(),
                    error=None,
                )
            except httpx.HTTPStatusError as e:
                log.warning("marker_http_error", status=e.response.status_code)
                # 429 = rate limited; 5xx = service issue
                code = (
                    "rate_limited" if e.response.status_code == 429
                    else f"http_{e.response.status_code}"
                )
                return TrademarkSearchResult(
                    jurisdiction=self.jurisdiction,
                    records=[],
                    duration_ms=elapsed(),
                    error=code,
                )
            except Exception as e:  # noqa: BLE001 — port contract: never raise
                log.exception("marker_search_unexpected_error")
                return TrademarkSearchResult(
                    jurisdiction=self.jurisdiction,
                    records=[],
                    duration_ms=elapsed(),
                    error=f"unexpected:{e.__class__.__name__}",
                )

    async def _search_once(self, phrase: str) -> list[TrademarkRecord]:
        """Execute one Marker API lookup."""
        # URL-encode the phrase — Marker is path-based, not query-based
        encoded_phrase = quote_plus(phrase)
        path = MARKER_SEARCH_PATH_TEMPLATE.format(phrase=encoded_phrase)

        # If creds provided, append (Marker premium tier)
        if self._username and self._password:
            path = (
                f"/api/v2/trademarks/trademark/{encoded_phrase}/start/1"
                f"/username/{self._username}/password/{self._password}"
            )

        async def _do() -> httpx.Response:
            response = await self._client.get(path)
            if response.status_code == 404:
                # Marker returns 404 for "no matches" sometimes
                return response
            response.raise_for_status()
            return response

        response = await run_with_retry(_do, service_name="marker", max_attempts=3)
        if response.status_code == 404:
            return []

        try:
            payload = response.json()
        except ValueError:
            logger.warning("marker_non_json_response")
            return []

        # Marker can return:
        #  {"count": 0}  → no matches
        #  {"count": N, "trademarks": [...]} → matches
        #  {"error": "..."} → quota exceeded or other issue
        if isinstance(payload, dict):
            if "error" in payload:
                logger.warning("marker_api_error", error=payload.get("error"))
                return []

            count = payload.get("count", 0)
            if count == 0:
                return []

            raw_items = payload.get("trademarks", [])
            if not isinstance(raw_items, list):
                return []
        elif isinstance(payload, list):
            raw_items = payload
        else:
            return []

        # Cap items processed (free tier returns up to 100, we keep top 50)
        records = [self._parse_item(item) for item in raw_items[:MAX_RESULTS]]
        return [r for r in records if r is not None]

    def _parse_item(self, item: dict[str, Any]) -> TrademarkRecord | None:
        """Convert a Marker API record to our normalized TrademarkRecord."""
        # Marker fields (verified from their docs):
        #   serial_number, registration_number, wordmark, code (status),
        #   description, owners, classes, registration_date, filing_date

        serial = (
            item.get("serial_number")
            or item.get("serialNumber")
            or item.get("registration_number")
        )
        if not serial:
            return None

        mark = (
            item.get("wordmark")
            or item.get("word")
            or item.get("mark")
            or ""
        )

        # Marker uses single-letter status codes — translate
        raw_code = item.get("code") or item.get("status") or ""
        raw_status = _translate_marker_status_code(raw_code)
        status = normalize_filing_status(raw_status)

        # Classes can be a list, string, or single int
        nice_classes = parse_nice_classes(item.get("classes") or item.get("class"))

        # Owner can be in 'owners' list or 'owner' string
        owner = _extract_owner(item)

        filing_date = normalize_date_string(item.get("filing_date") or item.get("filingDate"))
        registration_date = normalize_date_string(
            item.get("registration_date") or item.get("registrationDate")
        )

        is_active = status in ACTIVE_STATUSES
        is_pending = status == FilingStatus.PENDING

        return TrademarkRecord(
            registration_number=str(serial),
            mark=str(mark).strip() or "(no mark)",
            owner=owner,
            status=status,
            raw_status=str(raw_status) if raw_status else str(raw_code),
            nice_class=nice_classes[0] if nice_classes else None,
            nice_classes=nice_classes,
            filing_date=filing_date,
            registration_date=registration_date,
            jurisdiction=self.jurisdiction,
            source_url=USPTO_TSDR_URL_TEMPLATE.format(sn=serial),
            goods_services=item.get("description") or item.get("goods_services"),
            is_active=is_active,
            is_pending=is_pending,
        )


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


# Marker / USPTO single-letter status code mapping (subset).
# See https://markerapi.com/docs for full list.
_MARKER_STATUS_CODES: dict[str, str] = {
    "REGISTERED": "Registered",
    "LIVE": "Live",
    "DEAD": "Dead",
    "PENDING": "Pending",
    "ABANDONED": "Abandoned",
    "CANCELLED": "Cancelled",
    "EXPIRED": "Expired",
    "OPPOSED": "Opposition Pending",
    # Numeric/alpha USPTO status codes
    "700": "Registered",
    "800": "Pending",
    "900": "Abandoned",
}


def _translate_marker_status_code(code: str) -> str:
    """Map Marker's status code to a string our normalizer understands."""
    if not code:
        return ""
    upper = str(code).upper().strip()
    return _MARKER_STATUS_CODES.get(upper, upper)


def _extract_owner(item: dict[str, Any]) -> str | None:
    """Pull primary owner name from various possible Marker shapes."""
    # Direct string owner
    owner = item.get("owner")
    if isinstance(owner, str) and owner.strip():
        return owner.strip()

    # Owners list (most common)
    owners = item.get("owners")
    if isinstance(owners, list) and owners:
        first = owners[0]
        if isinstance(first, str) and first.strip():
            return first.strip()
        if isinstance(first, dict):
            for key in ("name", "owner_name", "ownerName", "party_name"):
                value = first.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

    # Single dict
    if isinstance(owner, dict):
        for key in ("name", "owner_name"):
            value = owner.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    return None


def _filter_by_classes(
    records: list[TrademarkRecord], nice_classes: list[int]
) -> list[TrademarkRecord]:
    """
    Keep only records that overlap one of the requested classes.

    Records with NO class data are KEPT (we'd rather over-report than miss
    a match because of incomplete metadata).
    """
    if not nice_classes:
        return records
    target = set(nice_classes)
    return [
        r for r in records
        if not r.nice_classes  # keep when class unknown
        or (set(r.nice_classes) & target)
    ]
