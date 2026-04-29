"""
IP Australia (ATMOSS) trademark search adapter.

Implements TrademarkAPI. IP Australia's public ATMOSS search doesn't expose
a documented JSON API for third parties; we use their search endpoint that
returns a JSON-ish payload in some modes.

This adapter is designed to degrade gracefully — if the endpoint is down or
returns unexpected data, we return an empty result with an `error` field.
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


IPAU_DEFAULT_BASE_URL = "https://search.ipaustralia.gov.au"
IPAU_SEARCH_PATH = "/trademarks/search/api/search"
MAX_RESULTS = 50

IPAU_DETAIL_URL_TEMPLATE = (
    "https://search.ipaustralia.gov.au/trademarks/search/view/{number}"
)


class IPAustraliaClient:
    """IP Australia (ATMOSS) trademark search client."""

    jurisdiction: JurisdictionCode = JurisdictionCode.AU

    def __init__(
        self,
        *,
        base_url: str = IPAU_DEFAULT_BASE_URL,
        http_factory: HttpClientFactory | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        if client is not None:
            self._client = client
            self._owns_client = False
        else:
            factory = http_factory or HttpClientFactory()
            self._client = factory.build(base_url=self._base_url)
            self._owns_client = True

    async def __aenter__(self) -> "IPAustraliaClient":
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
        log = logger.bind(service="ipau", phrase=phrase, nice_classes=nice_classes)
        async with measure_duration() as elapsed:
            try:
                # IP Australia's search supports multi-class filter via comma-sep list
                records = await self._search_once(phrase, nice_classes)

                # Filter client-side to requested classes (some hits may slip through)
                filtered = _filter_by_classes(records, nice_classes)
                deduped = _dedupe_records(filtered)

                log.info("ipau_search_complete", count=len(deduped), duration_ms=elapsed())
                return TrademarkSearchResult(
                    jurisdiction=self.jurisdiction,
                    records=deduped,
                    duration_ms=elapsed(),
                    error=None,
                )
            except httpx.HTTPStatusError as e:
                log.warning("ipau_http_error", status=e.response.status_code)
                return TrademarkSearchResult(
                    jurisdiction=self.jurisdiction,
                    records=[],
                    duration_ms=elapsed(),
                    error=f"http_{e.response.status_code}",
                )
            except Exception as e:  # noqa: BLE001
                log.exception("ipau_search_unexpected_error")
                return TrademarkSearchResult(
                    jurisdiction=self.jurisdiction,
                    records=[],
                    duration_ms=elapsed(),
                    error=f"unexpected:{e.__class__.__name__}",
                )

    async def _search_once(
        self, phrase: str, nice_classes: list[int]
    ) -> list[TrademarkRecord]:
        params = {
            "words": phrase,
            "classes": ",".join(str(c) for c in nice_classes),
            "limit": str(MAX_RESULTS),
        }

        async def _do() -> httpx.Response:
            response = await self._client.get(IPAU_SEARCH_PATH, params=params)
            if response.status_code == 404:
                return response
            response.raise_for_status()
            return response

        response = await run_with_retry(_do, service_name="ipau", max_attempts=3)
        if response.status_code == 404:
            return []

        try:
            payload = response.json()
        except ValueError:
            logger.warning("ipau_non_json_response")
            return []

        raw_items = _extract_items(payload)
        records = [self._parse_item(item) for item in raw_items]
        return [r for r in records if r is not None]

    def _parse_item(self, item: dict[str, Any]) -> TrademarkRecord | None:
        number = item.get("tmNumber") or item.get("number") or item.get("id")
        if not number:
            return None

        mark = item.get("tmWords") or item.get("words") or item.get("mark") or ""
        raw_status = item.get("status") or item.get("tmStatus")
        status = normalize_filing_status(raw_status)

        nice_classes = parse_nice_classes(
            item.get("classes") or item.get("niceClasses")
        )

        owner = _extract_owner(item)
        filing_date = normalize_date_string(item.get("lodgeDate") or item.get("filingDate"))
        registration_date = normalize_date_string(item.get("registrationDate"))

        is_active = status in ACTIVE_STATUSES
        is_pending = status == FilingStatus.PENDING

        return TrademarkRecord(
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
            source_url=IPAU_DETAIL_URL_TEMPLATE.format(number=number),
            goods_services=item.get("goodsAndServices") or item.get("goods"),
            is_active=is_active,
            is_pending=is_pending,
        )


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [i for i in payload if isinstance(i, dict)]
    if isinstance(payload, dict):
        for key in ("results", "data", "items", "hits", "trademarks"):
            value = payload.get(key)
            if isinstance(value, list):
                return [i for i in value if isinstance(i, dict)]
    return []


def _extract_owner(item: dict[str, Any]) -> str | None:
    for key in ("owner", "applicant", "ownerName"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            name = value.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
    return None


def _filter_by_classes(
    records: list[TrademarkRecord], nice_classes: list[int]
) -> list[TrademarkRecord]:
    """Keep only records that overlap one of the requested classes."""
    if not nice_classes:
        return records
    target = set(nice_classes)
    return [r for r in records if (set(r.nice_classes) & target) or not r.nice_classes]


def _dedupe_records(records: list[TrademarkRecord]) -> list[TrademarkRecord]:
    by_number: dict[str, TrademarkRecord] = {}
    for record in records:
        if record.registration_number not in by_number:
            by_number[record.registration_number] = record
    return list(by_number.values())
