"""
USPTO trademark search adapter.

Implements TrademarkAPI protocol. Uses the USPTO Open Data Portal JSON API.

API docs: https://developer.uspto.gov/api-catalog

Design:
- Single endpoint per search, per Nice class
- Results deduplicated by serial number across classes
- Failures → TrademarkSearchResult with `error` field (never raise)
- Adapter instance OWNS its httpx client; use async context manager
"""

from __future__ import annotations

import asyncio
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


USPTO_DEFAULT_BASE_URL = "https://tsdrapi.uspto.gov"
# The USPTO Trademark Search API endpoint. Their docs are in flux; we support
# the current documented shape and degrade gracefully if the shape changes.
USPTO_SEARCH_PATH = "/ts/cd/casedocs/statuses/search"

MAX_RESULTS_PER_CLASS = 50
TSDR_URL_TEMPLATE = (
    "https://tsdr.uspto.gov/#caseNumber={sn}&caseType=DEFAULT&searchType=statusSearch"
)


class USPTOClient:
    """USPTO trademark search client. Implements TrademarkAPI."""

    jurisdiction: JurisdictionCode = JurisdictionCode.US

    def __init__(
        self,
        *,
        base_url: str = USPTO_DEFAULT_BASE_URL,
        http_factory: HttpClientFactory | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        if client is not None:
            # Primarily for testing with respx
            self._client = client
            self._owns_client = False
        else:
            factory = http_factory or HttpClientFactory()
            self._client = factory.build(base_url=self._base_url)
            self._owns_client = True

    async def __aenter__(self) -> "USPTOClient":
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
        Search USPTO across all requested Nice classes in parallel.

        Dedupes results by serial number so a filing covering multiple classes
        isn't counted twice.
        """
        log = logger.bind(service="uspto", phrase=phrase, nice_classes=nice_classes)

        async with measure_duration() as elapsed:
            try:
                # Fan out one request per Nice class (USPTO only filters by one)
                results_per_class = await asyncio.gather(
                    *(self._search_one_class(phrase, nc) for nc in nice_classes),
                    return_exceptions=True,
                )

                combined: list[TrademarkRecord] = []
                error_messages: list[str] = []
                for nc, result in zip(nice_classes, results_per_class, strict=True):
                    if isinstance(result, BaseException):
                        error_messages.append(f"class_{nc}:{result.__class__.__name__}")
                        log.warning("uspto_class_search_failed", nice_class=nc, error=str(result))
                    else:
                        combined.extend(result)

                # Dedupe by registration_number
                deduped = _dedupe_records(combined)

                # If every class failed, we treat the whole search as errored
                if error_messages and not combined:
                    return TrademarkSearchResult(
                        jurisdiction=self.jurisdiction,
                        records=[],
                        duration_ms=elapsed(),
                        error=f"all_failed: {'; '.join(error_messages)}",
                    )

                log.info("uspto_search_complete", count=len(deduped), duration_ms=elapsed())
                return TrademarkSearchResult(
                    jurisdiction=self.jurisdiction,
                    records=deduped,
                    duration_ms=elapsed(),
                    error=None,
                )
            except Exception as e:  # noqa: BLE001 — port contract: never raise
                log.exception("uspto_search_unexpected_error")
                return TrademarkSearchResult(
                    jurisdiction=self.jurisdiction,
                    records=[],
                    duration_ms=elapsed(),
                    error=f"unexpected:{e.__class__.__name__}",
                )

    # ------------------------------------------------------------------
    # Per-class search
    # ------------------------------------------------------------------

    async def _search_one_class(
        self, phrase: str, nice_class: int
    ) -> list[TrademarkRecord]:
        """
        Query USPTO for one phrase + one Nice class. Returns parsed records.

        Raises on HTTP/network errors (caller aggregates via asyncio.gather).
        """
        params = {
            "q": phrase,
            "niceClass": str(nice_class),
            "limit": str(MAX_RESULTS_PER_CLASS),
        }

        async def _do_request() -> httpx.Response:
            response = await self._client.get(USPTO_SEARCH_PATH, params=params)
            if response.status_code == 404:
                # Tolerate "no results" 404s from this API
                return response
            response.raise_for_status()
            return response

        response = await run_with_retry(_do_request, service_name="uspto", max_attempts=3)

        if response.status_code == 404:
            return []

        try:
            payload = response.json()
        except ValueError:
            logger.warning("uspto_non_json_response", status=response.status_code)
            return []

        raw_items = _extract_items(payload)
        records = [self._parse_item(item, nice_class) for item in raw_items]
        return [r for r in records if r is not None]

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse_item(self, item: dict[str, Any], fallback_class: int) -> TrademarkRecord | None:
        """Convert a raw USPTO record to our normalized TrademarkRecord."""
        # The USPTO API fields vary by endpoint; we pick from common names.
        serial = (
            item.get("serialNumber")
            or item.get("serial_number")
            or item.get("applicationNumber")
        )
        if not serial:
            return None

        mark = (
            item.get("markIdentification")
            or item.get("markLiteralElement")
            or item.get("mark")
            or ""
        )
        raw_status = (
            item.get("statusDescription")
            or item.get("markCurrentStatusExternalDescriptionText")
            or item.get("status")
        )
        status = normalize_filing_status(raw_status)

        nice_classes = parse_nice_classes(
            item.get("niceClass")
            or item.get("classes")
            or item.get("internationalClasses")
        )
        if not nice_classes:
            nice_classes = [fallback_class]

        owner = _extract_owner(item)
        filing_date = normalize_date_string(item.get("filingDate"))
        registration_date = normalize_date_string(
            item.get("registrationDate") or item.get("registration_date")
        )

        is_active = status in ACTIVE_STATUSES
        is_pending = status == FilingStatus.PENDING

        return TrademarkRecord(
            registration_number=str(serial),
            mark=str(mark).strip() or "(no mark)",
            owner=owner,
            status=status,
            raw_status=raw_status,
            nice_class=nice_classes[0] if nice_classes else None,
            nice_classes=nice_classes,
            filing_date=filing_date,
            registration_date=registration_date,
            jurisdiction=self.jurisdiction,
            source_url=TSDR_URL_TEMPLATE.format(sn=serial),
            goods_services=item.get("goodsAndServices") or item.get("goods_services"),
            is_active=is_active,
            is_pending=is_pending,
        )


# -----------------------------------------------------------------------------
# Module-level helpers (pure, testable)
# -----------------------------------------------------------------------------


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    """Tolerantly unwrap results from whichever envelope USPTO returned."""
    if isinstance(payload, list):
        return [i for i in payload if isinstance(i, dict)]
    if isinstance(payload, dict):
        for key in ("results", "data", "items", "searchResults"):
            value = payload.get(key)
            if isinstance(value, list):
                return [i for i in value if isinstance(i, dict)]
    return []


def _extract_owner(item: dict[str, Any]) -> str | None:
    """Pull the primary owner name from whichever field holds it."""
    for key in ("ownerName", "owner", "currentOwner"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    # Sometimes owners are in a list of dicts
    owners = item.get("owners") or item.get("ownerList")
    if isinstance(owners, list) and owners:
        first = owners[0]
        if isinstance(first, dict):
            name = first.get("name") or first.get("partyName")
            if isinstance(name, str) and name.strip():
                return name.strip()
        elif isinstance(first, str):
            return first.strip() or None
    return None


def _dedupe_records(records: list[TrademarkRecord]) -> list[TrademarkRecord]:
    """Dedupe by registration_number; merge nice_classes when duplicated."""
    by_serial: dict[str, TrademarkRecord] = {}
    for record in records:
        existing = by_serial.get(record.registration_number)
        if existing is None:
            by_serial[record.registration_number] = record
            continue
        # Merge nice_classes
        merged_classes = list(existing.nice_classes)
        for nc in record.nice_classes:
            if nc not in merged_classes:
                merged_classes.append(nc)
        by_serial[record.registration_number] = existing.model_copy(
            update={"nice_classes": merged_classes}
        )
    return list(by_serial.values())
