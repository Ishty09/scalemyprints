"""
TMview API adapter — global trademark data via WIPO/EUIPO consortium.

TMview is the official trademark search platform of the European Union
Intellectual Property Office (EUIPO) and the World Intellectual Property
Organization (WIPO). It aggregates trademark data from 70+ jurisdictions
worldwide.

Why we use it:
- **Public**, no API key required
- Covers EUTM (EU), national EU members, WIPO international registrations
- Stable endpoint structure
- Free for reasonable usage

Implements TrademarkAPI for the EU jurisdiction (EUTM filings).

Endpoint reference: https://www.tmdn.org/tmview/api
"""

from __future__ import annotations

from types import TracebackType
from typing import Any

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

TMVIEW_DEFAULT_BASE_URL = "https://www.tmdn.org"
TMVIEW_SEARCH_PATH = "/tmview/api/search"
MAX_RESULTS = 50

TMVIEW_DETAIL_URL_TEMPLATE = (
    "https://www.tmdn.org/tmview/welcome#/tmview/detail/{office}/{number}"
)


class TMViewClient:
    """
    EU trademark search client using WIPO TMview public API.

    Targets EUTM (EU-wide trademarks) primarily but the underlying API
    covers all WIPO member states. We filter to EUTM + a few major EU
    national offices for relevance to POD sellers.
    """

    jurisdiction: JurisdictionCode = JurisdictionCode.EU

    # Office codes we consider "EU coverage" for POD context
    # EM = EUTM, ES/FR/DE/IT/NL = major EU national offices
    EU_OFFICE_CODES: frozenset[str] = frozenset({"EM", "ES", "FR", "DE", "IT", "NL"})

    def __init__(
        self,
        *,
        base_url: str = TMVIEW_DEFAULT_BASE_URL,
        http_factory: HttpClientFactory | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        if client is not None:
            self._client = client
            self._owns_client = False
        else:
            factory = http_factory or HttpClientFactory()
            # TMview requires a browser-like User-Agent
            self._client = factory.build(
                base_url=self._base_url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (compatible; ScaleMyPrints/0.1; "
                        "+https://scalemyprints.com)"
                    ),
                    "Accept": "application/json",
                },
            )
            self._owns_client = True

    async def __aenter__(self) -> "TMViewClient":
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

    async def search(
        self, phrase: str, nice_classes: list[int]
    ) -> TrademarkSearchResult:
        log = logger.bind(service="tmview", phrase=phrase, nice_classes=nice_classes)

        async with measure_duration() as elapsed:
            try:
                records = await self._search_once(phrase, nice_classes)
                # Filter: only EU offices + matching classes
                eu_records = [
                    r for r in records
                    if r.registration_number and self._is_eu_record(r)
                ]
                filtered = _filter_by_classes(eu_records, nice_classes)

                log.info("tmview_search_complete", count=len(filtered), duration_ms=elapsed())
                return TrademarkSearchResult(
                    jurisdiction=self.jurisdiction,
                    records=filtered,
                    duration_ms=elapsed(),
                    error=None,
                )
            except httpx.HTTPStatusError as e:
                log.warning("tmview_http_error", status=e.response.status_code)
                return TrademarkSearchResult(
                    jurisdiction=self.jurisdiction,
                    records=[],
                    duration_ms=elapsed(),
                    error=f"http_{e.response.status_code}",
                )
            except Exception as e:  # noqa: BLE001
                log.exception("tmview_search_unexpected_error")
                return TrademarkSearchResult(
                    jurisdiction=self.jurisdiction,
                    records=[],
                    duration_ms=elapsed(),
                    error=f"unexpected:{e.__class__.__name__}",
                )

    async def _search_once(
        self, phrase: str, nice_classes: list[int]
    ) -> list[TrademarkRecord]:
        # TMview's search endpoint accepts these params:
        params: dict[str, str] = {
            "criteria": "C",  # contains
            "basicSearch": phrase,
            "size": str(MAX_RESULTS),
            "page": "1",
            "language": "en",
            # Office filter: EM (EUTM) + 5 major EU national offices
            "offices": ",".join(self.EU_OFFICE_CODES),
        }
        if nice_classes:
            params["niceClass"] = ",".join(str(c) for c in nice_classes)

        async def _do() -> httpx.Response:
            response = await self._client.get(TMVIEW_SEARCH_PATH, params=params)
            if response.status_code == 404:
                return response
            response.raise_for_status()
            return response

        response = await run_with_retry(_do, service_name="tmview", max_attempts=3)
        if response.status_code == 404:
            return []

        try:
            payload = response.json()
        except ValueError:
            logger.warning("tmview_non_json_response")
            return []

        raw_items = _extract_items(payload)
        records = [self._parse_item(item) for item in raw_items]
        return [r for r in records if r is not None]

    def _parse_item(self, item: dict[str, Any]) -> TrademarkRecord | None:
        # TMview uses 'ST13' as the unique ID (office prefix + number)
        st13 = item.get("ST13") or item.get("st13") or item.get("id")
        number = item.get("applicationNumber") or item.get("registrationNumber") or st13
        if not number:
            return None

        mark = (
            item.get("tmName")
            or item.get("verbalElement")
            or item.get("mark")
            or item.get("name")
            or ""
        )
        raw_status = item.get("status") or item.get("statusCode")
        status = normalize_filing_status(raw_status)

        nice_classes = parse_nice_classes(
            item.get("niceClass") or item.get("classes")
        )

        owner = _extract_owner(item)
        filing_date = normalize_date_string(item.get("applicationDate") or item.get("filingDate"))
        registration_date = normalize_date_string(item.get("registrationDate"))

        # Office code embedded — used by _is_eu_record
        office_code = item.get("officeCode") or item.get("office") or ""

        is_active = status in ACTIVE_STATUSES
        is_pending = status == FilingStatus.PENDING

        # Compose source URL via ST13 if available
        source_url: str | None = None
        if st13:
            source_url = f"https://www.tmdn.org/tmview/welcome#/tmview/detail/{st13}"

        record = TrademarkRecord(
            registration_number=str(number),
            mark=str(mark).strip() or "(no mark)",
            owner=owner,
            status=status,
            raw_status=str(raw_status) if raw_status else None,
            nice_class=nice_classes[0] if nice_classes else None,
            nice_classes=nice_classes,
            filing_date=filing_date,
            registration_date=registration_date,
            jurisdiction=self.jurisdiction,
            source_url=source_url,
            goods_services=item.get("goodsServices"),
            is_active=is_active,
            is_pending=is_pending,
        )
        # Stash office code for filtering (won't survive Pydantic frozen, but we can recompute)
        return record

    def _is_eu_record(self, record: TrademarkRecord) -> bool:
        """
        Filter: keep records that match EU-relevant office codes.

        TMview returns global results; we narrow to EU. We infer office
        from registration number prefix when stored that way (e.g., 'EM-')
        or just accept all if we can't tell.
        """
        # Currently we filter at API level via offices=... param,
        # so this is just a passthrough. Belt-and-suspenders for future
        # if we widen the search.
        return True


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [i for i in payload if isinstance(i, dict)]
    if isinstance(payload, dict):
        for key in ("tradeMarks", "results", "items", "data", "trademarks"):
            value = payload.get(key)
            if isinstance(value, list):
                return [i for i in value if isinstance(i, dict)]
    return []


def _extract_owner(item: dict[str, Any]) -> str | None:
    """Pull owner from various possible TMview shapes."""
    # TMview exposes 'representativeName' and 'applicants' in different versions
    for key in ("applicantName", "applicant", "owner", "ownerName", "representativeName"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    # List of applicants
    applicants = item.get("applicants")
    if isinstance(applicants, list) and applicants:
        first = applicants[0]
        if isinstance(first, str):
            return first.strip() or None
        if isinstance(first, dict):
            for key in ("name", "applicantName"):
                value = first.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return None


def _filter_by_classes(
    records: list[TrademarkRecord], nice_classes: list[int]
) -> list[TrademarkRecord]:
    if not nice_classes:
        return records
    target = set(nice_classes)
    return [
        r for r in records
        if not r.nice_classes
        or (set(r.nice_classes) & target)
    ]
