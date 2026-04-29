"""
UK Intellectual Property Office (UKIPO) trademark adapter.

UKIPO doesn't expose a public REST API for the trademark register, but
their search portal (www.ipo.gov.uk) accepts queries that return JSON-like
responses through their AJAX endpoints.

We use a tolerant parser similar to IP Australia — happy path returns
real data, unhappy paths return empty results with `error` set.

Note: UK is post-Brexit (no longer covered by EUIPO). Sellers shipping to
the UK separately need this jurisdiction.
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

UKIPO_DEFAULT_BASE_URL = "https://trademarks.ipo.gov.uk"
UKIPO_SEARCH_PATH = "/trademark/api/search"
MAX_RESULTS = 50

UKIPO_DETAIL_URL_TEMPLATE = (
    "https://trademarks.ipo.gov.uk/ipo-tmcase/page/Results/1/UK{number}"
)


class UKIPOClient:
    """UK Intellectual Property Office trademark search client."""

    jurisdiction: JurisdictionCode = JurisdictionCode.UK

    def __init__(
        self,
        *,
        base_url: str = UKIPO_DEFAULT_BASE_URL,
        http_factory: HttpClientFactory | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        if client is not None:
            self._client = client
            self._owns_client = False
        else:
            factory = http_factory or HttpClientFactory()
            # UKIPO sometimes blocks non-browser User-Agents
            self._client = factory.build(
                base_url=self._base_url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; ScaleMyPrints/0.1)"},
            )
            self._owns_client = True

    async def __aenter__(self) -> "UKIPOClient":
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
        log = logger.bind(service="ukipo", phrase=phrase, nice_classes=nice_classes)
        async with measure_duration() as elapsed:
            try:
                records = await self._search_once(phrase, nice_classes)
                filtered = _filter_by_classes(records, nice_classes)

                log.info("ukipo_search_complete", count=len(filtered), duration_ms=elapsed())
                return TrademarkSearchResult(
                    jurisdiction=self.jurisdiction,
                    records=filtered,
                    duration_ms=elapsed(),
                    error=None,
                )
            except httpx.HTTPStatusError as e:
                log.warning("ukipo_http_error", status=e.response.status_code)
                return TrademarkSearchResult(
                    jurisdiction=self.jurisdiction,
                    records=[],
                    duration_ms=elapsed(),
                    error=f"http_{e.response.status_code}",
                )
            except Exception as e:  # noqa: BLE001
                log.exception("ukipo_search_unexpected_error")
                return TrademarkSearchResult(
                    jurisdiction=self.jurisdiction,
                    records=[],
                    duration_ms=elapsed(),
                    error=f"unexpected:{e.__class__.__name__}",
                )

    async def _search_once(
        self, phrase: str, nice_classes: list[int]
    ) -> list[TrademarkRecord]:
        params: dict[str, str] = {
            "q": phrase,
            "limit": str(MAX_RESULTS),
        }
        # UK search supports class filter as comma-separated list
        if nice_classes:
            params["classes"] = ",".join(str(c) for c in nice_classes)

        async def _do() -> httpx.Response:
            response = await self._client.get(UKIPO_SEARCH_PATH, params=params)
            if response.status_code == 404:
                return response
            response.raise_for_status()
            return response

        response = await run_with_retry(_do, service_name="ukipo", max_attempts=3)
        if response.status_code == 404:
            return []

        try:
            payload = response.json()
        except ValueError:
            logger.warning("ukipo_non_json_response")
            return []

        raw_items = _extract_items(payload)
        records = [self._parse_item(item) for item in raw_items]
        return [r for r in records if r is not None]

    def _parse_item(self, item: dict[str, Any]) -> TrademarkRecord | None:
        number = (
            item.get("trademarkNumber")
            or item.get("number")
            or item.get("applicationNumber")
            or item.get("id")
        )
        if not number:
            return None

        mark = (
            item.get("mark")
            or item.get("trademarkText")
            or item.get("title")
            or item.get("words")
            or ""
        )
        raw_status = item.get("status") or item.get("trademarkStatus")
        status = normalize_filing_status(raw_status)

        nice_classes = parse_nice_classes(
            item.get("classes") or item.get("niceClasses") or item.get("classifications")
        )

        owner = _extract_owner(item)
        filing_date = normalize_date_string(item.get("filingDate") or item.get("applicationDate"))
        registration_date = normalize_date_string(
            item.get("registrationDate") or item.get("dateOfRegistration")
        )

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
            source_url=UKIPO_DETAIL_URL_TEMPLATE.format(number=number),
            goods_services=item.get("goodsAndServices") or item.get("specification"),
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
        for key in ("results", "data", "items", "trademarks", "hits"):
            value = payload.get(key)
            if isinstance(value, list):
                return [i for i in value if isinstance(i, dict)]
    return []


def _extract_owner(item: dict[str, Any]) -> str | None:
    for key in ("owner", "ownerName", "applicant", "applicantName", "proprietor"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            name = value.get("name") or value.get("displayName")
            if isinstance(name, str) and name.strip():
                return name.strip()
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
